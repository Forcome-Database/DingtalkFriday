"""
FastAPI main application entry point.

Registers all routers, configures CORS middleware, and initializes
the database on startup.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import async_session, init_db
from app.routers import admin, analytics, auth, departments, export, leave, sync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# APScheduler instance (created lazily)
_scheduler = None


async def _ensure_admin_users() -> None:
    """Ensure all admin phone numbers are in the allowed_user table."""
    if not settings.admin_phones:
        return
    phones = [p.strip() for p in settings.admin_phones.split(",") if p.strip()]
    if not phones:
        return

    from sqlalchemy import select
    from app.models import AllowedUser

    async with async_session() as session:
        for phone in phones:
            result = await session.execute(
                select(AllowedUser).where(AllowedUser.mobile == phone)
            )
            if not result.scalar_one_or_none():
                session.add(AllowedUser(
                    mobile=phone,
                    name="管理员",
                    created_at=datetime.utcnow(),
                ))
                logger.info("Added admin phone %s to allowed_user table", phone)
        await session.commit()


def _setup_scheduler():
    """Set up APScheduler with cron-based sync if configured."""
    global _scheduler
    cron_expr = settings.sync_cron.strip()
    if not cron_expr:
        logger.info("SYNC_CRON not set, scheduled sync disabled")
        return

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = AsyncIOScheduler()
        trigger = CronTrigger.from_crontab(cron_expr)

        async def scheduled_sync():
            """Run full sync as a scheduled job."""
            logger.info("Scheduled sync triggered by cron: %s", cron_expr)
            try:
                from app.services.sync import full_sync
                await full_sync()
            except Exception as e:
                logger.exception("Scheduled sync failed: %s", e)

        _scheduler.add_job(scheduled_sync, trigger, id="scheduled_sync", replace_existing=True)
        _scheduler.start()
        logger.info("APScheduler started with cron: %s", cron_expr)
    except Exception as e:
        logger.exception("Failed to setup scheduler: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup: ensure data directory exists and initialize DB tables
    os.makedirs("data", exist_ok=True)
    await init_db()
    logger.info("Database initialized")

    # Log loaded config for debugging
    from app.auth import _get_admin_phones
    logger.info("ADMIN_PHONES config: %r → parsed: %s", settings.admin_phones, _get_admin_phones())

    # Ensure admin users are in allowed_user table
    await _ensure_admin_users()

    # Start scheduled sync if configured
    _setup_scheduler()

    yield

    # Shutdown: stop scheduler and close DingTalk HTTP client
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down")

    from app.dingtalk.client import dingtalk_client
    await dingtalk_client.close()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Employee Leave Management System",
    description="DingTalk-integrated leave data query and export system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow frontend dev server
# Note: "*" with allow_credentials=True is invalid per CORS spec.
# In dev, requests go through Vite proxy so CORS is not needed.
# In production, nginx serves both frontend and API on the same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(departments.router)
app.include_router(leave.router)
app.include_router(export.router)
app.include_router(sync.router)
app.include_router(analytics.router)


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


# Mount static files for frontend build output (optional, for production)
# The frontend build artifacts should be placed in backend/static/
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
