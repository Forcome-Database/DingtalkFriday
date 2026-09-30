"""
Trip (business trip / out-of-office) sync service.

Syncs data from DingTalk getupdatedata API into trip_record table
using a partitioned caching strategy (hot/warm/cold zones).
"""

import asyncio
import logging
import random
from weakref import WeakValueDictionary
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError

from app.database import async_session
from app.event_models import ApprovalScope, AttendanceRefresh
from app.models import Employee, TripRecord, TripSyncCursor, SyncLog
from app.dingtalk.attendance import get_update_data
from app.dingtalk.client import DingTalkClientError, dingtalk_client
from app.config import settings
from app.services.durations import allocate_hours_by_date, business_today

logger = logging.getLogger(__name__)
_trip_sync_reserved = False
_day_locks: WeakValueDictionary = WeakValueDictionary()


class TripDataPending(RuntimeError):
    """Attendance has not yet produced an authoritative date result."""


def is_trip_sync_running() -> bool:
    return _trip_sync_reserved


def reserve_trip_sync() -> bool:
    global _trip_sync_reserved
    if _trip_sync_reserved:
        return False
    _trip_sync_reserved = True
    return True


def _approval_allocation(item: dict) -> dict:
    start = datetime.fromisoformat(str(item["begin_time"]).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(item["end_time"]).replace("Z", "+00:00"))
    total = float(item["duration"])
    unit = str(item.get("duration_unit", "")).lower()
    if unit in {"day", "days", "天"}:
        day_unit = True
        total *= 8.0
    elif unit in {"hour", "hours", "小时"}:
        day_unit = False
    else:
        raise ValueError("Unknown approval duration unit")
    return allocate_hours_by_date(start, end, total, calendar_days=True, day_unit=day_unit)


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
    today = business_today()
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


async def _sync_one(userid: str, work_date_str: str, semaphore: asyncio.Semaphore, *, require_settled: bool = False) -> int:
    key = (userid, work_date_str)
    lock = _day_locks.setdefault(key, asyncio.Lock())
    async with lock:
        return await _sync_one_impl(userid, work_date_str, semaphore, require_settled=require_settled)


async def _sync_one_impl(userid: str, work_date_str: str, semaphore: asyncio.Semaphore, *, require_settled: bool = False) -> int:
    """Sync trip records for one user on one date.

    Returns count of records upserted. Uses a delete-then-insert strategy
    to ensure stale approvals (e.g., revoked trips) are removed.
    Skips deletion when the API returns empty data (unsettled date)
    to avoid wiping valid records.
    """
    async with semaphore:
        data = await get_update_data(userid, work_date_str)

        # If the API returned an empty result, attendance for this date
        # has not been calculated yet — preserve existing records.
        if not data:
            if require_settled:
                raise TripDataPending()
            return 0

        approve_list = data.get("approve_list") or []

        async with async_session() as session:
            revoked_ids = set((await session.execute(select(ApprovalScope.instance_id).where(
                ApprovalScope.userid == userid,
                ApprovalScope.status.in_(["TERMINATED", "REVOKED", "REPLACED", "DELETED"]),
            ))).scalars().all())

        # Filter biz_type=2 (trip/outing)
        trip_items = [a for a in approve_list if a.get("biz_type") == 2
                      and (a.get("procInst_id") or a.get("proc_inst_id")) not in revoked_ids]
        prepared = []
        seen = set()
        for item in trip_items:
            proc_inst_id = item.get("procInst_id") or item.get("proc_inst_id")
            if not proc_inst_id:
                raise ValueError("Trip approval is missing its instance ID")
            if proc_inst_id in seen:
                continue
            seen.add(proc_inst_id)
            try:
                allocation = _approval_allocation(item)
            except (KeyError, TypeError) as exc:
                raise ValueError("Trip approval has incomplete duration data") from exc
            hours = allocation.get(date.fromisoformat(work_date_str), 0.0)
            if hours > 0:
                prepared.append((item, proc_inst_id, hours))

        now = datetime.now(timezone.utc)

        # Retry a locked SQLite transaction with the same fetched source data.
        for attempt in range(3):
            try:
                async with async_session() as session:
                    await session.execute(delete(TripRecord).where(
                        TripRecord.userid == userid,
                        TripRecord.work_date == work_date_str,
                    ))
                    for item, proc_inst_id, duration_hours in prepared:
                        session.add(TripRecord(
                            userid=userid,
                            work_date=work_date_str,
                            tag_name=item.get("tag_name", ""),
                            sub_type=item.get("sub_type"),
                            begin_time=str(item.get("begin_time", "")),
                            end_time=str(item.get("end_time", "")),
                            duration_hours=duration_hours,
                            source_duration=float(item["duration"]),
                            source_duration_unit=item["duration_unit"],
                            proc_inst_id=proc_inst_id,
                            last_synced_at=now,
                            created_at=now,
                        ))
                    stmt = sqlite_insert(TripSyncCursor).values(
                        userid=userid, work_date=work_date_str, last_synced_at=now,
                    ).on_conflict_do_update(
                        index_elements=["userid", "work_date"], set_={"last_synced_at": now},
                    )
                    await session.execute(stmt)
                    await session.commit()
                break
            except OperationalError as exc:
                error_code = getattr(exc.orig, "sqlite_errorcode", 0) or 0
                if error_code & 255 not in {5, 6} or attempt == 2:
                    raise
                await asyncio.sleep(0.1 * 2 ** attempt)

        return len(prepared)


async def sync_trip_records(force_month: Optional[str] = None, *, reserved: bool = False, recover_gap: bool = False) -> str:
    global _trip_sync_reserved
    if not reserved and not reserve_trip_sync():
        return "Trip sync is already running"
    try:
        return await _sync_trip_records(force_month, recover_gap=recover_gap)
    finally:
        _trip_sync_reserved = False


async def _sync_trip_records(force_month: Optional[str] = None, *, recover_gap: bool = False) -> str:
    """Main sync entry point.

    Args:
        force_month: If provided (YYYY-MM), sync that entire month ignoring cache.
                     Otherwise applies hot/warm partitioned caching strategy.

    Returns:
        Summary message string.
    """
    log_id = await _create_sync_log()
    from app.services.events import trip_coverage_epoch
    coverage_epoch = trip_coverage_epoch()
    try:
        # Get all employee userids
        async with async_session() as session:
            result = await session.execute(select(Employee.userid))
            all_userids = [row[0] for row in result.fetchall()]

        if not all_userids:
            msg = "No employees found, skipping trip sync"
            await _finish_sync_log(log_id, "failed", msg)
            return msg

        # Detect new employees (no cursor records at all) for backfill
        new_userids: set = set()
        if not force_month:
            async with async_session() as session:
                result = await session.execute(
                    select(TripSyncCursor.userid).distinct()
                )
                known_userids = {row[0] for row in result.fetchall()}
            new_userids = set(all_userids) - known_userids
            if new_userids:
                logger.info(
                    "Detected %d new employees for full-year backfill",
                    len(new_userids),
                )

        # Build date list based on sync mode
        if force_month:
            dates = _build_force_month_dates(force_month)
            zone = "force"
        else:
            is_monday = business_today().weekday() == 0
            dates = _build_date_list(
                hot_past=settings.trip_hot_days_past,
                hot_future=settings.trip_hot_days_future,
                warm_future=settings.trip_warm_days_future,
                include_warm=is_monday or recover_gap,
            )
            zone = "hot"  # Default zone; overridden per-date below

        # Build full-year date list for new employee backfill
        backfill_dates: set = set()
        if new_userids and not force_month:
            year_start = date(business_today().year, 1, 1)
            year_end = min(
                date(business_today().year, 12, 31),
                business_today() + timedelta(days=settings.trip_hot_days_future),
            )
            d = year_start
            while d <= year_end:
                backfill_dates.add(d)
                d += timedelta(days=1)
            # Remove dates already in the normal sync list
            backfill_dates -= set(dates)
            logger.info(
                "Backfill: %d extra dates for %d new employees",
                len(backfill_dates), len(new_userids),
            )

        today = business_today()
        hot_start = today - timedelta(days=settings.trip_hot_days_past)
        hot_end = today + timedelta(days=settings.trip_hot_days_future)

        semaphore = asyncio.Semaphore(settings.trip_sync_concurrency)
        total_records = 0
        total_skipped = 0
        total_backfill = 0
        consecutive_failures = 0
        total_failures = 0
        request_start = dingtalk_client.request_counts().get("/topapi/attendance/getupdatedata", 0)
        async with async_session() as session:
            cursor_rows = (await session.execute(select(TripSyncCursor))).scalars().all()
            cursors = {(row.userid, row.work_date): row.last_synced_at for row in cursor_rows}

        def warm_is_fresh(uid, work_date):
            synced_at = cursors.get((uid, work_date))
            if synced_at is None:
                return False
            age = datetime.now(timezone.utc) - synced_at.replace(tzinfo=timezone.utc)
            return age.total_seconds() < 7 * 86400

        async def run_batch(batch):
            nonlocal total_failures, consecutive_failures

            async def run_one(uid, work_date):
                for attempt in range(settings.trip_sync_retry_count + 1):
                    try:
                        return await _sync_one(uid, work_date, semaphore)
                    except Exception as exc:
                        retryable = isinstance(exc, DingTalkClientError) and exc.retryable
                        if not retryable or attempt >= settings.trip_sync_retry_count:
                            error_code = getattr(getattr(exc, "orig", None), "sqlite_errorcode", None)
                            error = type(exc).__name__ + (f":sqlite:{error_code}" if error_code is not None else "")
                            async with async_session() as session:
                                await session.execute(sqlite_insert(AttendanceRefresh).values(
                                    domain="trip", userid=uid, date_key=work_date,
                                    attempts=1, error=error,
                                    next_attempt_at=datetime.utcnow() + timedelta(seconds=10),
                                ).on_conflict_do_update(
                                    index_elements=["domain", "userid", "date_key"],
                                    set_={"error": error, "next_attempt_at": datetime.utcnow() + timedelta(seconds=10)},
                                ))
                                await session.commit()
                            logger.warning("Trip date refresh failed on %s: %s", work_date, error)
                            return None
                        await asyncio.sleep(2 ** attempt + random.uniform(0, 0.25))

            results = await asyncio.gather(*(run_one(uid, work_date) for uid, work_date in batch))
            for result in results:
                if result is None:
                    consecutive_failures += 1
                    total_failures += 1
                else:
                    consecutive_failures = 0
            return sum(result for result in results if result is not None)

        # --- Phase 1: Normal sync for all employees ---
        for d in dates:
            work_date_str = d.isoformat()

            # Determine zone for non-forced syncs
            if not force_month:
                zone = "hot" if hot_start <= d <= hot_end else "warm"

            tasks = []
            for uid in all_userids:
                # Skip check applies only to warm zone
                if zone != "hot" and zone != "force" and not recover_gap:
                    should_skip = warm_is_fresh(uid, work_date_str)
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

                total_records += await run_batch(batch)

        # --- Phase 2: Backfill new employees for dates outside normal range ---
        if backfill_dates and consecutive_failures < settings.trip_sync_fail_threshold:
            sorted_backfill = sorted(backfill_dates)
            for d in sorted_backfill:
                if consecutive_failures >= settings.trip_sync_fail_threshold:
                    break
                work_date_str = d.isoformat()
                tasks = [(uid, work_date_str) for uid in new_userids]

                for batch_start in range(0, len(tasks), batch_size):
                    batch = tasks[batch_start: batch_start + batch_size]

                    total_backfill += await run_batch(batch)

            logger.info("Backfill done: %d records for new employees", total_backfill)

        # Cleanup stale cursors older than 1 year to keep the table lean
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        async with async_session() as session:
            await session.execute(
                delete(TripSyncCursor).where(TripSyncCursor.last_synced_at < cutoff)
            )
            await session.commit()

        backfill_info = ""
        if total_backfill > 0:
            backfill_info = f", {total_backfill} backfill records for {len(new_userids)} new employees"
        msg = (
            f"Trip sync done: {total_records} records across "
            f"{len(all_userids)} employees, {len(dates)} dates, "
            f"{total_skipped} skipped, {total_failures} failures, "
            f"{dingtalk_client.request_counts().get('/topapi/attendance/getupdatedata', 0) - request_start} requests{backfill_info}"
        )
        await _finish_sync_log(log_id, "failed" if total_failures else "success", msg)
        if not total_failures and not force_month and recover_gap:
            from app.services.events import mark_trip_coverage_complete
            mark_trip_coverage_complete(coverage_epoch)
        logger.info(msg)
        return msg

    except Exception as e:
        msg = f"Trip sync failed: {e}"
        await _finish_sync_log(log_id, "failed", msg)
        logger.exception(msg)
        raise
