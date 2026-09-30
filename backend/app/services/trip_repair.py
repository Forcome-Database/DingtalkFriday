"""Repair stored trip hours from authoritative approval totals, preserving rows."""

import logging
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from app.database import async_session
from app.dingtalk.attendance import get_update_data
from app.dingtalk.client import DingTalkClientError, dingtalk_client
from app.models import TripRecord
from app.services.trip_sync import _approval_allocation

logger = logging.getLogger(__name__)
API_PATH = "/topapi/attendance/getupdatedata"


class _ConcurrentChange(Exception):
    pass


def _source(item):
    allocation = _approval_allocation(item)
    return {
        "allocation": allocation,
        "source_duration": float(item["duration"]),
        "source_duration_unit": str(item["duration_unit"]),
        "begin_time": str(item["begin_time"]),
        "end_time": str(item["end_time"]),
    }


def _fingerprint(source):
    return (
        source["source_duration"], source["source_duration_unit"].lower(),
        source["begin_time"], source["end_time"],
    )


def _local_consistency(records):
    try:
        sources = [
            _source({
                "begin_time": row.begin_time, "end_time": row.end_time,
                "duration": row.source_duration, "duration_unit": row.source_duration_unit,
            }) for row in records
        ]
        fingerprints = defaultdict(set)
        for source in sources:
            fingerprints[(source["begin_time"], source["end_time"])].add(_fingerprint(source))
        if any(len(values) != 1 for values in fingerprints.values()):
            return "conflicting"
        for row, source in zip(records, sources):
            expected = source["allocation"].get(date.fromisoformat(row.work_date), 0.0)
            if not math.isclose(row.duration_hours, expected, abs_tol=1e-6):
                return "hours_mismatch"
        return "consistent"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "invalid"


async def repair_trip_durations(
    year: Optional[int] = None,
    *,
    dry_run: bool = True,
    only_missing_source: bool = True,
    max_requests: Optional[int] = None,
    minimum_work_date: Optional[date] = None,
) -> dict:
    """Resolve each original approval range and repair existing rows only.

    Select user/date requests greedily by the unresolved approvals they cover.
    A range total is reused only for stored dates with the same original range,
    never inferred from historical hours. An approval can contain multiple
    itinerary rows with different ranges. Dry runs read the authoritative API.
    """
    if year is not None and not 1 <= year <= 9999:
        raise ValueError("Year must be between 1 and 9999")
    if max_requests is not None and max_requests < 0:
        raise ValueError("Request limit must be non-negative")
    if minimum_work_date is not None and (not isinstance(minimum_work_date, date) or isinstance(minimum_work_date, datetime)):
        raise ValueError("Minimum work date must be a date")

    async with async_session() as session:
        query = select(TripRecord).order_by(TripRecord.userid, TripRecord.work_date, TripRecord.id)
        if year is not None:
            query = query.where(TripRecord.work_date >= f"{year:04d}-01-01", TripRecord.work_date <= f"{year:04d}-12-31")
        rows = (await session.execute(query)).scalars().all()

    groups = defaultdict(list)
    for row in rows:
        groups[(row.userid, row.proc_inst_id, row.begin_time, row.end_time)].append(row)
    candidates = {
        key: records for key, records in groups.items()
        if not only_missing_source or any(row.source_duration is None or not row.source_duration_unit for row in records)
    }
    report = {
        "dryRun": dry_run,
        "year": year,
        "minimumWorkDate": minimum_work_date.isoformat() if minimum_work_date else None,
        "skippedHistoricalQueries": 0,
        "selectedRows": len(rows),
        "candidateApprovals": len({key[:2] for key in candidates}),
        "candidateRanges": len(candidates),
        "skippedSourceApprovals": len({key[:2] for key in groups} - {key[:2] for key in candidates}),
        "skippedSourceRanges": len(groups) - len(candidates),
        "requests": 0,
        "httpRequests": 0,
        "resolvedApprovals": 0,
        "resolvedRanges": 0,
        "partiallyResolvedApprovals": 0,
        "plannedChanges": 0,
        "updatedRows": 0,
        "hoursBefore": math.fsum(row.duration_hours for row in rows),
        "hoursAfter": 0.0,
        "corrections": [],
        "unresolved": [],
        "skippedSources": [
            {
                "userid": key[0], "approvalId": key[1],
                "beginTime": key[2], "endTime": key[3],
                "recordIds": [row.id for row in records],
                "reason": "source_metadata_present_not_revalidated",
                "localConsistency": _local_consistency(records),
            } for key, records in groups.items() if key not in candidates
        ],
    }
    pending = set(candidates)
    query_groups = defaultdict(set)
    reasons = {}
    attempts = defaultdict(list)
    skipped_pairs = set()
    for key, records in candidates.items():
        if not key[0] or not key[1]:
            reasons[key] = "missing_identity"
            pending.remove(key)
            continue
        try:
            for row in records:
                date.fromisoformat(row.work_date)
        except ValueError:
            reasons[key] = "invalid_stored_date"
            pending.remove(key)
            continue
        eligible_dates = 0
        for row in records:
            if minimum_work_date is not None and date.fromisoformat(row.work_date) < minimum_work_date:
                skipped_pairs.add((row.userid, row.work_date))
                continue
            eligible_dates += 1
            query_groups[(row.userid, row.work_date)].add(key)
        if not eligible_dates:
            reasons[key] = "history_outside_attendance_window"
            pending.remove(key)
    report["skippedHistoricalQueries"] = len(skipped_pairs)

    sources = {}
    queried = set()
    request_start = dingtalk_client.request_counts().get(API_PATH, 0)
    while pending:
        options = [
            (pair, len(keys & pending)) for pair, keys in query_groups.items()
            if pair not in queried and keys & pending
        ]
        if not options:
            break
        if max_requests is not None and report["requests"] >= max_requests:
            for key in pending:
                reasons[key] = "request_limit"
            break
        pair, _ = min(options, key=lambda option: (-option[1], option[0]))
        queried.add(pair)
        affected = query_groups[pair] & pending
        for key in affected:
            attempts[key].append(pair[1])
        report["requests"] += 1
        try:
            response = await get_update_data(*pair)
            if not isinstance(response, dict):
                raise ValueError("Invalid attendance response")
            items = response.get("approve_list") or []
            if not isinstance(items, list):
                raise ValueError("Invalid approval list")
        except Exception as exc:
            error_code = f":{exc.errcode}" if isinstance(exc, DingTalkClientError) else ""
            logger.warning("Trip repair query failed: %s%s", type(exc).__name__, error_code)
            for key in affected:
                reasons[key] = f"query_failed:{type(exc).__name__}{error_code}"
            continue

        parsed = {}
        invalid = set()
        returned_approvals = set()
        for item in items:
            if not isinstance(item, dict) or item.get("biz_type") != 2:
                continue
            approval_id = item.get("procInst_id") or item.get("proc_inst_id")
            if not isinstance(approval_id, (str, int)):
                continue
            returned_approvals.add((pair[0], str(approval_id)))
            key = (pair[0], str(approval_id), str(item.get("begin_time")), str(item.get("end_time")))
            if key not in pending:
                continue
            try:
                source = _source(item)
            except (KeyError, TypeError, ValueError, OverflowError):
                invalid.add(key)
                reasons[key] = "invalid_authority_duration"
                continue
            if key in parsed and _fingerprint(parsed[key]) != _fingerprint(source):
                invalid.add(key)
                reasons[key] = "conflicting_authority_values"
                continue
            parsed[key] = source
        for key, source in parsed.items():
            if key not in invalid:
                sources[key] = source
                pending.remove(key)
                reasons.pop(key, None)
        for key in affected & pending:
            reasons.setdefault(key, "approval_range_not_returned" if key[:2] in returned_approvals else "approval_not_returned")

    report["httpRequests"] = dingtalk_client.request_counts().get(API_PATH, 0) - request_start
    candidate_approval_ranges = defaultdict(set)
    for key in candidates:
        candidate_approval_ranges[key[:2]].add(key)
    report["resolvedRanges"] = len(sources)
    report["resolvedApprovals"] = sum(keys <= sources.keys() for keys in candidate_approval_ranges.values())
    report["partiallyResolvedApprovals"] = sum(bool(keys & sources.keys()) and not keys <= sources.keys() for keys in candidate_approval_ranges.values())
    plans = {}
    now = datetime.now(timezone.utc)
    for key, source in sources.items():
        changes = []
        for row in candidates[key]:
            values = {field: source[field] for field in ("source_duration", "source_duration_unit", "begin_time", "end_time")}
            values["duration_hours"] = source["allocation"].get(date.fromisoformat(row.work_date), 0.0)
            if all(getattr(row, field) == value for field, value in values.items()):
                continue
            values["last_synced_at"] = now
            changes.append((row, values))
            report["corrections"].append({
                "recordId": row.id, "userid": row.userid, "approvalId": row.proc_inst_id,
                "workDate": row.work_date, "oldHours": row.duration_hours,
                "newHours": values["duration_hours"], "sourceDuration": source["source_duration"],
                "sourceUnit": source["source_duration_unit"], "applied": False,
                "sourceBegin": source["begin_time"], "sourceEnd": source["end_time"],
            })
        if changes:
            plans[key] = changes
    report["plannedChanges"] = len(report["corrections"])

    if not dry_run:
        for key, changes in plans.items():
            try:
                async with async_session() as session:
                    async with session.begin():
                        for row, values in changes:
                            conditions = [TripRecord.id == row.id]
                            # A sync may replace rows while API reads are in flight.
                            for field in ("userid", "work_date", "proc_inst_id", "duration_hours", "source_duration", "source_duration_unit", "begin_time", "end_time", "last_synced_at"):
                                expected = getattr(row, field)
                                column = getattr(TripRecord, field)
                                conditions.append(column.is_(None) if expected is None else column == expected)
                            result = await session.execute(update(TripRecord).where(*conditions).values(**values))
                            if result.rowcount != 1:
                                raise _ConcurrentChange()
            except _ConcurrentChange:
                reasons[key] = "concurrent_change_preserved"
                continue
            report["updatedRows"] += len(changes)
            changed_ids = {row.id for row, _ in changes}
            for correction in report["corrections"]:
                if correction["recordId"] in changed_ids:
                    correction["applied"] = True

    for key in sorted(candidates):
        if key not in sources or key in reasons:
            report["unresolved"].append({
                "userid": key[0], "approvalId": key[1],
                "beginTime": key[2], "endTime": key[3],
                "recordIds": [row.id for row in candidates[key]],
                "attemptedDates": attempts[key],
                "reason": reasons.get(key, "approval_not_returned"),
            })
    report["unresolvedRanges"] = len(report["unresolved"])
    report["unresolvedApprovals"] = len({(item["userid"], item["approvalId"]) for item in report["unresolved"]})
    if dry_run:
        proposed = {item["recordId"]: item["newHours"] for item in report["corrections"]}
        report["hoursAfter"] = math.fsum(proposed.get(row.id, row.duration_hours) for row in rows)
    else:
        async with async_session() as session:
            values = (await session.execute(select(TripRecord.duration_hours).where(TripRecord.id.in_([row.id for row in rows])))).scalars().all()
        report["hoursAfter"] = math.fsum(values)
    report["hoursDelta"] = report["hoursAfter"] - report["hoursBefore"]
    report["plannedHoursDelta"] = math.fsum(item["newHours"] - item["oldHours"] for item in report["corrections"])
    report["appliedHoursDelta"] = math.fsum(item["newHours"] - item["oldHours"] for item in report["corrections"] if item["applied"])
    logger.info("Trip repair: %d calls, %d planned rows, %d updated rows, %d unresolved ranges", report["requests"], report["plannedChanges"], report["updatedRows"], report["unresolvedRanges"])
    return report
