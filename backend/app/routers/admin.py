"""
Admin API router - manage allowed users.

GET    /api/admin/users          - List all allowed users
POST   /api/admin/users          - Add a new allowed user
DELETE /api/admin/users/{mobile}  - Remove an allowed user
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth import require_admin, _get_admin_phones
from app.database import async_session
from app.models import AllowedUser
from app.schemas import AddUserRequest, AllowedUserOut, MessageResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=List[AllowedUserOut])
async def list_users(_admin=Depends(require_admin)):
    """List all allowed users."""
    admin_phones = _get_admin_phones()
    async with async_session() as session:
        result = await session.execute(
            select(AllowedUser).order_by(AllowedUser.id)
        )
        users = result.scalars().all()
    return [
        AllowedUserOut(
            id=u.id,
            mobile=u.mobile,
            name=u.name,
            userid=u.userid,
            created_at=u.created_at,
            isAdmin=u.mobile in admin_phones,
        )
        for u in users
    ]


@router.post("/users", response_model=AllowedUserOut)
async def add_user(request: AddUserRequest, _admin=Depends(require_admin)):
    """Add a new allowed user by phone number."""
    async with async_session() as session:
        # Check if already exists
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
            created_at=datetime.utcnow(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return AllowedUserOut(
        id=user.id,
        mobile=user.mobile,
        name=user.name,
        userid=user.userid,
        created_at=user.created_at,
    )


@router.delete("/users/{mobile}", response_model=MessageResponse)
async def remove_user(mobile: str, _admin=Depends(require_admin)):
    """Remove an allowed user by phone number."""
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

    return MessageResponse(message=f"User {mobile} removed", success=True)
