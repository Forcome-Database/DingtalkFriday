"""Read today's pending leave evidence without exposing employee identities."""

import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fingerprint(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:10]


async def run():
    from sqlalchemy import select
    from app.database import async_session, engine
    from app.dingtalk.attendance import get_update_data
    from app.dingtalk.client import dingtalk_client
    from app.models import LeaveRecord
    from app.services.durations import BUSINESS_TIMEZONE, business_today

    logging.disable(logging.WARNING)
    today = business_today()
    first = datetime.combine(today, datetime.min.time(), BUSINESS_TIMEZONE)
    last = first + timedelta(days=1)
    async with async_session() as session:
        rows = (await session.execute(select(LeaveRecord).where(
            LeaveRecord.status == "\u5f85\u590d\u6838",
            LeaveRecord.start_time < int(last.timestamp() * 1000),
            LeaveRecord.end_time > int(first.timestamp() * 1000),
        ))).scalars().all()
    evidence = {}
    try:
        for row in rows:
            if row.userid in evidence:
                continue
            response = await get_update_data(row.userid, today.isoformat())
            approvals = []
            for item in response.get("approve_list", []):
                instance_id = item.get("procInst_id") or item.get("proc_inst_id")
                entry = {key: item.get(key) for key in (
                    "biz_type", "begin_time", "end_time", "duration", "duration_unit",
                )}
                entry["instance"] = fingerprint(instance_id)
                if instance_id:
                    try:
                        detail = await dingtalk_client.workflow_instance(instance_id)
                        entry["workflow"] = {
                            "status": detail.get("status"), "result": detail.get("result"),
                            "bizAction": detail.get("bizAction"),
                            "attachments": len(detail.get("attachedProcessInstanceIds") or []),
                            "originatorMatches": (detail.get("originatorUserId") == row.userid),
                        }
                    except Exception as exc:
                        entry["workflowError"] = type(exc).__name__
                approvals.append(entry)
            evidence[row.userid] = approvals
        report = []
        for row in rows:
            report.append({
                "employee": fingerprint(row.userid),
                "start": datetime.fromtimestamp(row.start_time / 1000, BUSINESS_TIMEZONE).isoformat(),
                "end": datetime.fromtimestamp(row.end_time / 1000, BUSINESS_TIMEZONE).isoformat(),
                "duration": row.duration_percent, "unit": row.duration_unit,
                "note": row.sync_note, "attendanceApprovals": evidence[row.userid],
            })
        print(json.dumps({"date": today.isoformat(), "pending": report}, ensure_ascii=True))
    finally:
        await dingtalk_client.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
