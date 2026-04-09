"""
Trip (business trip / out-of-office) sync service.

Syncs data from DingTalk getupdatedata API into trip_record table
using a partitioned caching strategy (hot/warm/cold zones).
"""

import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import async_session
from app.models import Employee, TripRecord, TripSyncCursor, SyncLog
from app.dingtalk.attendance import get_update_data
from app.config import settings

logger = logging.getLogger(__name__)


async def _create_sync_log(sync_type: str = "trip_record") -> int:
    """Create a 'running' sync log entry and return its ID."""
    async with async_session() as session:
        log = SyncLog(
            sync_type=sync_type,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log.id


async def _finish_sync_log(log_id: int, status: str, message: str = "") -> None:
    """Mark a sync log entry as finished."""
    async with async_session() as session:
        result = await session.execute(select(SyncLog).where(SyncLog.id == log_id))
        log = result.scalar_one_or_none()
        if log:
            log.status = status
            log.message = message
            log.finished_at = datetime.now(timezone.utc)
            await session.commit()


def _build_date_list(
    hot_past: int,
    hot_future: int,
    warm_future: int,
    include_warm: bool,
) -> List[date]:
    """Build the list of dates to sync based on zone configuration.

    Hot zone (always synced): today-hot_past .. today+hot_future
    Warm zone (synced only on designated days): today+hot_future+1 .. today+warm_future
    """
    today = date.today()
    dates = set()

    # Hot zone: always included
    for delta in range(-hot_past, hot_future + 1):
        dates.add(today + timedelta(days=delta))

    # Warm zone: only on designated days (e.g., Monday)
    if include_warm:
        for delta in range(hot_future + 1, warm_future + 1):
            dates.add(today + timedelta(days=delta))

    return sorted(dates)


def _build_force_month_dates(month_str: str) -> List[date]:
    """Build date list for a specific month (YYYY-MM)."""
    year, month = int(month_str[:4]), int(month_str[5:7])
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    dates = []
    d = first_day
    while d <= last_day:
        dates.append(d)
        d += timedelta(days=1)
    return dates


async def _should_skip(userid: str, work_date: str, zone: str) -> bool:
    """Check if a (userid, work_date) should be skipped based on zone.

    Hot zone is never skipped. Warm zone is skipped if synced within 7 days.
    """
    if zone == "hot":
        return False  # Hot zone always syncs

    async with async_session() as session:
        result = await session.execute(
            select(TripSyncCursor).where(
                TripSyncCursor.userid == userid,
                TripSyncCursor.work_date == work_date,
            )
        )
        cursor = result.scalar_one_or_none()

    if cursor is None:
        return False  # Never synced, don't skip

    # Warm zone: skip if synced within 7 days
    age = datetime.now(timezone.utc) - cursor.last_synced_at.replace(tzinfo=timezone.utc)
    return age.total_seconds() < 7 * 86400


async def _sync_one(userid: str, work_date_str: str, semaphore: asyncio.Semaphore) -> int:
    """Sync trip records for one user on one date.

    Returns count of records upserted. Uses a delete-then-insert strategy
    to ensure stale approvals (e.g., revoked trips) are removed.
    Skips deletion when the API returns empty data (unsettled date)
    to avoid wiping valid records.
    """
    async with semaphore:
        await asyncio.sleep(0.05)  # 50ms throttle to avoid API rate limits

        data = await get_update_data(userid, work_date_str)

        # If the API returned an empty result, attendance for this date
        # has not been calculated yet — preserve existing records.
        if not data:
            return 0

        approve_list = data.get("approve_list") or []

        # Filter biz_type=2 (trip/outing)
        trip_items = [a for a in approve_list if a.get("biz_type") == 2]

        now = datetime.now(timezone.utc)

        # API returned valid attendance data — safe to delete-then-insert
        async with async_session() as session:
            await session.execute(
                delete(TripRecord).where(
                    TripRecord.userid == userid,
                    TripRecord.work_date == work_date_str,
                )
            )

            for item in trip_items:
                proc_inst_id = item.get("procInst_id") or item.get("proc_inst_id", "")
                if not proc_inst_id:
                    continue

                tag_name = item.get("tag_name", "")

                # Determine duration_hours for this day
                duration_raw = item.get("duration")
                duration_unit = item.get("duration_unit", "")
                if duration_raw is not None:
                    try:
                        dur = float(duration_raw)
                        # If unit is in days, convert to hours (8h per work day)
                        if "day" in duration_unit.lower() or "天" in duration_unit:
                            duration_hours = dur * 8
                        else:
                            duration_hours = dur
                        # Cap at 8 hours per day
                        duration_hours = min(duration_hours, 8.0)
                    except (ValueError, TypeError):
                        duration_hours = 8.0
                else:
                    duration_hours = 8.0  # Default full day

                session.add(TripRecord(
                    userid=userid,
                    work_date=work_date_str,
                    tag_name=tag_name,
                    sub_type=item.get("sub_type"),
                    begin_time=str(item.get("begin_time", "")),
                    end_time=str(item.get("end_time", "")),
                    duration_hours=duration_hours,
                    proc_inst_id=proc_inst_id,
                    last_synced_at=now,
                    created_at=now,
                ))

            # Upsert sync cursor to track last sync time for this (userid, work_date)
            stmt = sqlite_insert(TripSyncCursor).values(
                userid=userid,
                work_date=work_date_str,
                last_synced_at=now,
            ).on_conflict_do_update(
                index_elements=["userid", "work_date"],
                set_={"last_synced_at": now},
            )
            await session.execute(stmt)
            await session.commit()

        return len(trip_items)


async def sync_trip_records(force_month: Optional[str] = None) -> str:
    """Main sync entry point.

    Args:
        force_month: If provided (YYYY-MM), sync that entire month ignoring cache.
                     Otherwise applies hot/warm partitioned caching strategy.

    Returns:
        Summary message string.
    """
    log_id = await _create_sync_log()
    try:
        # Get all employee userids
        async with async_session() as session:
            result = await session.execute(select(Employee.userid))
            all_userids = [row[0] for row in result.fetchall()]

        if not all_userids:
            msg = "No employees found, skipping trip sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Build date list based on sync mode
        if force_month:
            dates = _build_force_month_dates(force_month)
            # Clear cursors for the forced month so _should_skip won't block anything
            async with async_session() as session:
                for d in dates:
                    await session.execute(
                        delete(TripSyncCursor).where(
                            TripSyncCursor.work_date == d.isoformat(),
                        )
                    )
                await session.commit()
            zone = "force"
        else:
            is_monday = date.today().weekday() == 0
            dates = _build_date_list(
                hot_past=settings.trip_hot_days_past,
                hot_future=settings.trip_hot_days_future,
                warm_future=settings.trip_warm_days_future,
                include_warm=is_monday,
            )
            zone = "hot"  # Default zone; overridden per-date below

        today = date.today()
        hot_start = today - timedelta(days=settings.trip_hot_days_past)
        hot_end = today + timedelta(days=settings.trip_hot_days_future)

        semaphore = asyncio.Semaphore(settings.trip_sync_concurrency)
        total_records = 0
        total_skipped = 0
        consecutive_failures = 0

        for d in dates:
            work_date_str = d.isoformat()

            # Determine zone for non-forced syncs
            if not force_month:
                zone = "hot" if hot_start <= d <= hot_end else "warm"

            tasks = []
            for uid in all_userids:
                # Skip check applies only to warm zone
                if zone != "hot" and zone != "force":
                    should_skip = await _should_skip(uid, work_date_str, zone)
                    if should_skip:
                        total_skipped += 1
                        continue
                tasks.append((uid, work_date_str))

            # Process in batches to allow failure threshold checking between batches
            batch_size = settings.trip_sync_concurrency * 5  # ~50 concurrent tasks per batch
            for batch_start in range(0, len(tasks), batch_size):
                if consecutive_failures >= settings.trip_sync_fail_threshold:
                    msg = f"Aborted: {consecutive_failures} consecutive failures"
                    await _finish_sync_log(log_id, "failed", msg)
                    return msg

                batch = tasks[batch_start: batch_start + batch_size]

                async def _sync_with_retry(uid, wds):
                    nonlocal total_records, consecutive_failures
                    for attempt in range(settings.trip_sync_retry_count + 1):
                        try:
                            count = await _sync_one(uid, wds, semaphore)
                            total_records += count
                            consecutive_failures = 0
                            return
                        except Exception as e:
                            if attempt >= settings.trip_sync_retry_count:
                                consecutive_failures += 1
                                logger.warning(
                                    "Failed to sync trip for %s on %s after %d retries: %s",
                                    uid, wds, settings.trip_sync_retry_count, e,
                                )
                                return
                            await asyncio.sleep(2 ** attempt)  # exponential back-off: 1s, 2s, 4s

                await asyncio.gather(
                    *[_sync_with_retry(uid, wds) for uid, wds in batch]
                )

        # Cleanup stale cursors older than 1 year to keep the table lean
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        async with async_session() as session:
            await session.execute(
                delete(TripSyncCursor).where(TripSyncCursor.last_synced_at < cutoff)
            )
            await session.commit()

        msg = (
            f"Trip sync done: {total_records} records across "
            f"{len(all_userids)} employees, {len(dates)} dates, "
            f"{total_skipped} skipped"
        )
        await _finish_sync_log(log_id, "success", msg)
        logger.info(msg)
        return msg

    except Exception as e:
        msg = f"Trip sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise
