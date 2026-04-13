"""
Admin API router - manage allowed users.

GET    /api/admin/users          - List all allowed users
POST   /api/admin/users          - Add a new allowed user
PUT    /api/admin/users/{mobile} - Update user name and/or role
DELETE /api/admin/users/{mobile} - Remove an allowed user
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth import require_admin, _get_admin_phones, invalidate_whitelist_cache
from app.database import async_session
from app.models import AllowedUser
from app.schemas import (
    AddUserRequest, AllowedUserOut, MessageResponse, UpdateUserRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_ROLES = ("admin", "user")


def _user_to_out(u: AllowedUser, admin_phones: list[str]) -> AllowedUserOut:
    role = getattr(u, "role", None) or "user"
    return AllowedUserOut(
        id=u.id,
        mobile=u.mobile,
        name=u.name,
        userid=u.userid,
        role=role,
        created_at=u.created_at,
        isAdmin=role == "admin" or u.mobile in admin_phones,
    )


@router.get("/users", response_model=List[AllowedUserOut])
async def list_users(_admin=Depends(require_admin)):
    """List all allowed users."""
    admin_phones = _get_admin_phones()
    async with async_session() as session:
        result = await session.execute(
            select(AllowedUser).order_by(AllowedUser.id)
        )
        users = result.scalars().all()
    return [_user_to_out(u, admin_phones) for u in users]


@router.post("/users", response_model=AllowedUserOut)
async def add_user(request: AddUserRequest, _admin=Depends(require_admin)):
    """Add a new allowed user by phone number with optional role."""
    if request.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role}. Must be one of {VALID_ROLES}",
        )

    async with async_session() as session:
        result = await session.execute(
            select(AllowedUser).where(AllowedUser.mobile == request.mobile)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with mobile {request.mobile} already exists",
            )

        user = AllowedUser(
            mobile=request.mobile,
            name=request.name,
            role=request.role,
            created_at=datetime.utcnow(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    invalidate_whitelist_cache(request.mobile)
    admin_phones = _get_admin_phones()
    return _user_to_out(user, admin_phones)


@router.put("/users/{mobile}", response_model=AllowedUserOut)
async def update_user(
    mobile: str, request: UpdateUserRequest, _admin=Depends(require_admin),
):
    """Update an allowed user's name and/or role."""
    if mobile == _admin.get("mobile") and request.role and request.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能降级自己的管理员权限",
        )
    if request.role is not None and request.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role}. Must be one of {VALID_ROLES}",
        )

    async with async_session() as session:
        result = await session.execute(
            select(AllowedUser).where(AllowedUser.mobile == mobile)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with mobile {mobile} not found",
            )
        if request.name is not None:
            user.name = request.name
        if request.role is not None:
            user.role = request.role
        session.add(user)
        await session.commit()
        await session.refresh(user)

    invalidate_whitelist_cache(mobile)
    admin_phones = _get_admin_phones()
    return _user_to_out(user, admin_phones)


@router.delete("/users/{mobile}", response_model=MessageResponse)
async def remove_user(mobile: str, _admin=Depends(require_admin)):
    """Remove an allowed user by phone number."""
    if mobile == _admin.get("mobile"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除自己的访问权限",
        )
    async with async_session() as session:
        result = await session.execute(
            select(AllowedUser).where(AllowedUser.mobile == mobile)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with mobile {mobile} not found",
            )
        await session.delete(user)
        await session.commit()

    invalidate_whitelist_cache(mobile)
    return MessageResponse(message=f"User {mobile} removed", success=True)
