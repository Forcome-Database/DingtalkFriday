"""Verify the deployed HTTP contracts without printing authentication data."""

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(args):
    import httpx
    from sqlalchemy import func, select
    from app.auth import create_token
    from app.config import settings
    from app.database import async_session, engine
    from app.dingtalk.client import dingtalk_client
    from app.event_models import EventInbox
    from app.models import AllowedUser, Department, Employee, LeaveRecord, TripRecord
    from app.services.durations import BUSINESS_TIMEZONE, business_today

    logging.disable(logging.WARNING)
    async with async_session() as session:
        operator = (await session.execute(select(AllowedUser).where(
            AllowedUser.role == "admin"
        ).limit(1))).scalar_one()
    token = create_token(operator.userid or "runtime-verification", "Runtime verification", operator.mobile)
    today = args.date or business_today()
    report = {}
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60,
                                     headers={"Authorization": "Bearer " + token}) as http:
            async def read(path, **params):
                response = await http.get(path, params=params)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {path}")
                return response.json()

            if args.trigger:
                path = "/api/sync" if args.trigger == "leave" else "/api/trip/sync"
                response = await http.post(path, json={"year": today.year} if args.trigger == "leave" else {})
                report["trigger"] = {"http": response.status_code, **response.json()}
            if args.event_test:
                from app.services.events import InboxHandler
                async with async_session() as session:
                    row = (await session.execute(select(TripRecord).where(
                        TripRecord.duration_hours > 0
                    ).order_by(TripRecord.work_date.desc()).limit(1))).scalar_one()
                event_id = "runtime-verification-" + datetime.utcnow().isoformat()
                code, _ = await InboxHandler().process(SimpleNamespace(
                    headers=SimpleNamespace(event_id=event_id, message_id=event_id,
                                            event_type="bpms_instance_change"),
                    data={"processInstanceId": row.proc_inst_id, "staffId": row.userid, "type": "finish"},
                ))
                report["eventTest"] = {"eventId": event_id, "ack": code}
            sync_status = await read("/api/sync/status")
            report["sync"] = {key: value for key, value in sync_status.items() if key != "logs"}
            report["health"] = await read("/api/health")
            if args.counts:
                leave_count = await read("/api/leave/daily-leave-count", year=today.year, month=today.month)
                leave_detail = await read("/api/leave/today-detail", date=today.isoformat())
                trip_summary = await read("/api/trip/monthly-summary", year=today.year, pageSize=100)
                trip_detail = await read("/api/trip/today", date=today.isoformat())
                leave_items = leave_detail.get("records", [])
                trip_items = trip_detail.get("list", [])
                leave_people = len({item["userid"] for item in leave_items})
                trip_people = len({item["employeeId"] for item in trip_items})
                report["counts"] = dict(date=today.isoformat(), leave=leave_count.get("todayCount"),
                                        leaveDetailPeople=leave_people, leaveDetailRecords=len(leave_items),
                                        trip=trip_summary["stats"].get("todayTotalCount"),
                                        tripDetailPeople=trip_people, tripStats=trip_summary["stats"])
                if report["counts"]["leave"] != leave_people or report["counts"]["trip"] != trip_people:
                    raise RuntimeError("Today headcount and HTTP detail disagree")
                async with async_session() as session:
                    report["inventory"] = {}
                    for model in (Department, Employee, LeaveRecord, TripRecord):
                        report["inventory"][model.__tablename__] = (await session.execute(
                            select(func.count()).select_from(model)
                        )).scalar_one()
                    first = int(datetime.combine(today, datetime.min.time(), BUSINESS_TIMEZONE).timestamp() * 1000)
                    last = first + 86400000 - 1
                    report["counts"]["pendingLeavePeople"] = (await session.execute(select(func.count(func.distinct(LeaveRecord.userid))).where(
                        LeaveRecord.status == "\u5f85\u590d\u6838", LeaveRecord.start_time <= last,
                        LeaveRecord.end_time >= first,
                    ))).scalar_one()
                    first_date = (today - timedelta(days=settings.trip_hot_days_past)).isoformat()
                    last_date = (today + timedelta(days=settings.trip_warm_days_future)).isoformat()
                    known_pairs = (await session.execute(select(TripRecord.userid, TripRecord.work_date).where(
                        TripRecord.work_date >= first_date, TripRecord.work_date <= last_date,
                    ).distinct())).all()
                    employee_count = report["inventory"]["employee"]
                    report["optimization"] = {
                        "retainedEmployees": employee_count,
                        "dailyFullScanRequests": employee_count * (settings.trip_hot_days_past + settings.trip_hot_days_future + 1),
                        "gapRecoveryScanRequests": employee_count * (settings.trip_hot_days_past + max(settings.trip_hot_days_future, settings.trip_warm_days_future) + 1),
                        "normalCompensationQueuedPairs": len(known_pairs),
                        "extraEventAndRetryRequestsExcluded": True,
                    }
            async with async_session() as session:
                report["eventInbox"] = (await session.execute(select(
                    func.count(), func.count(EventInbox.processed_at)
                ).select_from(EventInbox))).one()._asdict()
        print(json.dumps(report, default=str, ensure_ascii=True))
    finally:
        await dingtalk_client.close()
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", choices=["leave", "trip"])
    parser.add_argument("--event-test", action="store_true", help="Enqueue a diagnostic refresh of an existing approval")
    parser.add_argument("--counts", action="store_true")
    parser.add_argument("--date", type=date.fromisoformat, help="Inspect leave counts for a fixed business date")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
