"""
Data sync API router.

POST /api/sync          - Trigger full data sync (runs in background)
GET  /api/sync/status   - Query recent sync status
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from app.database import async_session
from app.models import SyncLog
from app.schemas import (
    MessageResponse,
    SyncStatusOut,
    SyncStatusResponse,
    SyncTriggerRequest,
)
from app.services.sync import full_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["sync"])

# Track whether a sync is currently running
_sync_lock = asyncio.Lock()


async def _run_sync(year: Optional[int] = None) -> None:
    """Background task that runs the full sync."""
    async with _sync_lock:
        try:
            await full_sync(year)
        except Exception as e:
            logger.exception("Background sync failed: %s", e)


@router.post("/sync", response_model=MessageResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    request: Optional[SyncTriggerRequest] = None,
):
    """
    Trigger a full data sync in the background.
    Returns immediately while the sync runs asynchronously.
    """
    if _sync_lock.locked():
        return MessageResponse(
            message="A sync is already running, please wait.",
            success=False,
        )

    year = request.year if request else None
    background_tasks.add_task(_run_sync, year)

    return MessageResponse(
        message="Sync started in background",
        success=True,
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def sync_status():
    """
    Get the most recent sync log entries (up to 20).
    """
    async with async_session() as session:
        result = await session.execute(
            select(SyncLog).order_by(SyncLog.id.desc()).limit(20)
        )
        logs = result.scalars().all()

    return SyncStatusResponse(
        logs=[
            SyncStatusOut(
                id=log.id,
                sync_type=log.sync_type,
                status=log.status,
                message=log.message,
                started_at=log.started_at,
                finished_at=log.finished_at,
            )
            for log in logs
        ]
    )
