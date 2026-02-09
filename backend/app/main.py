"""
FastAPI main application entry point.

Registers all routers, configures CORS middleware, and initializes
the database on startup.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import analytics, departments, leave, export, sync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup: ensure data directory exists and initialize DB tables
    os.makedirs("data", exist_ok=True)
    await init_db()
    logger.info("Database initialized")
    yield
    # Shutdown: close DingTalk HTTP client
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
