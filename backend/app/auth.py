"""
JWT utilities and FastAPI authentication dependencies.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)


def _get_admin_phones() -> list[str]:
    """Parse admin phone numbers from config."""
    if not settings.admin_phones:
        return []
    return [p.strip() for p in settings.admin_phones.split(",") if p.strip()]


def create_token(userid: str, name: str, mobile: str) -> str:
    """Create a JWT token for the given user."""
    payload = {
        "userid": userid,
        "name": name,
        "mobile": mobile,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency: extract and verify JWT from Authorization header.
    Returns the token payload dict with keys: userid, name, mobile.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = auth_header[7:]
    payload = decode_token(token)
    return payload


async def require_admin(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    FastAPI dependency: require the current user to be an admin.
    Admin is determined by checking if user's mobile is in ADMIN_PHONES.
    """
    admin_phones = _get_admin_phones()
    if user.get("mobile") not in admin_phones:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
