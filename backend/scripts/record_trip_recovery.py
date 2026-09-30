"""Record verified coverage recovery while retaining the original failed log."""

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(args):
    from sqlalchemy import func, select
    from app.database import async_session, engine
    from app.models import Employee, SyncLog, TripSyncCursor

    task_id = f"trip-recovery:{args.log_id}"
    try:
        async with async_session() as session:
            existing = (await session.execute(select(SyncLog).where(
                SyncLog.task_id == task_id,
            ))).scalar_one_or_none()
            if existing:
                print(json.dumps({"alreadyRecorded": True, "logId": existing.id}))
                return
            failed = await session.get(SyncLog, args.log_id)
            if not failed or failed.sync_type != "trip_record" or failed.status != "failed" or not failed.started_at:
                raise ValueError("A failed trip coverage log is required")
            latest = (await session.execute(select(SyncLog).where(
                SyncLog.sync_type == "trip_record",
            ).order_by(SyncLog.id.desc()).limit(1))).scalar_one()
            if latest.id != failed.id:
                raise ValueError("A newer trip task exists; review its result first")
            userids = (await session.execute(select(Employee.userid))).scalars().all()
            days = (args.last_date - args.first_date).days + 1
            if not userids or not 1 <= days <= 366:
                raise ValueError("Invalid employee scope or date range")
            expected = len(userids) * days
            covered = (await session.execute(select(func.count()).select_from(TripSyncCursor).where(
                TripSyncCursor.userid.in_(userids),
                TripSyncCursor.work_date >= args.first_date.isoformat(),
                TripSyncCursor.work_date <= args.last_date.isoformat(),
                TripSyncCursor.last_synced_at >= failed.started_at,
            ))).scalar_one()
            if covered != expected:
                raise ValueError(f"Coverage is incomplete: {covered}/{expected} employee dates")
            recovery = SyncLog(
                task_id=task_id, sync_type="trip_record", status="success",
                started_at=failed.started_at, finished_at=datetime.utcnow(),
                message=(f"Verified recovery of failed trip task {failed.id}: {len(userids)} employees, "
                         f"{args.first_date}..{args.last_date}, {covered} employee dates, "
                         f"{args.repair_requests} targeted repair requests; original failure log retained"),
            )
            session.add(recovery)
            await session.commit()
            print(json.dumps({"logId": recovery.id, "covered": covered, "originalFailureRetained": True}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-id", type=int, required=True)
    parser.add_argument("--first-date", type=date.fromisoformat, required=True)
    parser.add_argument("--last-date", type=date.fromisoformat, required=True)
    parser.add_argument("--repair-requests", type=int, required=True)
    arguments = parser.parse_args()
    if arguments.repair_requests < 0:
        parser.error("--repair-requests must be non-negative")
    asyncio.run(run(arguments))
