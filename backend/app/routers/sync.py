"""Sync triggers and domain-specific freshness information."""

from datetime import timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.auth import get_current_user, require_admin
from app.database import async_session
from app.models import LeaveRecord, SyncLog
from app.schemas import MessageResponse, SyncStatusOut, SyncStatusResponse, SyncTriggerRequest
from app.services.sync import full_sync_task_id, is_full_sync_running, is_leave_sync_running, start_full_sync

router = APIRouter(prefix="/api", tags=["sync"])


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _log_out(log) -> Optional[SyncStatusOut]:
    if log is None:
        return None
    return SyncStatusOut(id=log.id, task_id=log.task_id, sync_type=log.sync_type, status=log.status,
                         message=log.message, started_at=_utc(log.started_at), finished_at=_utc(log.finished_at))


@router.post("/sync", response_model=MessageResponse)
async def trigger_sync(request: Optional[SyncTriggerRequest] = None, _admin=Depends(require_admin)):
    year = request.year if request else None
    created = start_full_sync(year)
    return MessageResponse(message="Sync started in background" if created else "This year's sync is already running",
                           success=created, taskId=full_sync_task_id(year))


@router.get("/sync/status", response_model=SyncStatusResponse)
async def sync_status(_user=Depends(get_current_user), taskId: Annotated[Optional[str], Query()] = None):
    from app.services.trip_sync import is_trip_sync_running
    from app.services.events import event_status

    running = {"full": is_full_sync_running(), "trip": is_trip_sync_running()}
    async with async_session() as session:
        task_log = (await session.execute(select(SyncLog).where(
            SyncLog.sync_type == "full", SyncLog.task_id == taskId,
        ).order_by(SyncLog.id.desc()).limit(1))).scalar_one_or_none() if taskId else None
        logs = (await session.execute(select(SyncLog).order_by(SyncLog.id.desc()).limit(20))).scalars().all()
        latest = {}
        success = {}
        for sync_type in ("full", "leave_record", "leave_record_incremental", "trip_record"):
            latest[sync_type] = (await session.execute(select(SyncLog).where(
                SyncLog.sync_type == sync_type
            ).order_by(SyncLog.id.desc()).limit(1))).scalar_one_or_none()
            success[sync_type] = (await session.execute(select(SyncLog).where(
                SyncLog.sync_type == sync_type, SyncLog.status == "success"
            ).order_by(SyncLog.id.desc()).limit(1))).scalar_one_or_none()
        pending_count = (await session.execute(select(func.count()).select_from(LeaveRecord).where(
            LeaveRecord.status == "待复核"
        ))).scalar_one()

    freshness = {}
    for domain, sync_type in (("leave", "leave_record"), ("trip", "trip_record")):
        current = latest[sync_type]
        last_success = success[sync_type]
        domain_running = (running["full"] or is_leave_sync_running()) if domain == "leave" else running["trip"]
        if domain == "leave" and latest["leave_record_incremental"] is not None:
            incremental = latest["leave_record_incremental"]
            if current is None or (incremental.status == "failed" and incremental.id > current.id):
                current = incremental
        if domain == "leave" and latest["full"] is not None:
            full_log = latest["full"]
            if full_log.status == "failed" and (current is None or full_log.id > current.id):
                current = full_log
        pending = pending_count if domain == "leave" else 0
        state = ("running" if domain_running else "never" if current is None
                 else "failed" if current.status in {"failed", "running"} else "warning" if pending else "fresh")
        freshness[domain] = dict(last_success_at=_utc(last_success.finished_at) if last_success else None,
                                 state=state, message=current.message if current else None, pending_count=pending)
    return SyncStatusResponse(logs=[_log_out(log) for log in logs], task=_log_out(task_log),
                              latest={"full": _log_out(latest["full"]), "trip": _log_out(latest["trip_record"])},
                              running=running, freshness=freshness, events=await event_status())
