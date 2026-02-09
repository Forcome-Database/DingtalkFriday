"""
Authentication API router.

GET  /api/auth/config    - Get DingTalk corpId for frontend JSAPI
POST /api/auth/dingtalk  - DingTalk H5 micro-app login (authCode exchange)
GET  /api/auth/me        - Get current user info
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth import create_token, get_current_user, _get_admin_phones
from app.config import settings
from app.database import async_session
from app.dingtalk.user import get_user_detail, get_user_info_by_code
from app.models import AllowedUser, Employee
from app.schemas import (
    AuthConfigResponse,
    DingTalkLoginRequest,
    LoginResponse,
    UserInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    """Return DingTalk corpId for frontend JSAPI initialization."""
    return AuthConfigResponse(corpId=settings.dingtalk_corp_id)


@router.post("/dingtalk", response_model=LoginResponse)
async def dingtalk_login(request: DingTalkLoginRequest):
    """
    DingTalk H5 micro-app login flow:
    1. Frontend calls dd.runtime.permission.requestAuthCode → authCode
    2. Exchange authCode for userid via /topapi/v2/user/getuserinfo
    3. Fetch user detail (name, mobile, avatar) via /topapi/v2/user/get
    4. Check if mobile is in allowed_user table
    5. Issue JWT token
    """
    try:
        # Step 1: Exchange auth code for userid
        user_info = await get_user_info_by_code(request.authCode)
        userid = user_info.get("userid")
        if not userid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get userid from DingTalk auth code",
            )

        # Step 2: Get full user detail
        detail = await get_user_detail(userid)
        name = detail.get("name", "")
        mobile = detail.get("mobile", "")
        avatar = detail.get("avatar", "")

        if not mobile:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot retrieve phone number from DingTalk. Access denied.",
            )

        # Step 3: Check if user is allowed
        admin_phones = _get_admin_phones()
        is_admin = mobile in admin_phones

        async with async_session() as session:
            result = await session.execute(
                select(AllowedUser).where(AllowedUser.mobile == mobile)
            )
            allowed = result.scalar_one_or_none()

        if not allowed and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有访问权限，请联系管理员开通",
            )

        # Step 4: Update employee mobile field
        async with async_session() as session:
            result = await session.execute(
                select(Employee).where(Employee.userid == userid)
            )
            emp = result.scalar_one_or_none()
            if emp and not emp.mobile:
                emp.mobile = mobile
                session.add(emp)
                await session.commit()

        # Step 5: Update allowed_user userid if missing
        if allowed and not allowed.userid:
            async with async_session() as session:
                result = await session.execute(
                    select(AllowedUser).where(AllowedUser.mobile == mobile)
                )
                au = result.scalar_one_or_none()
                if au:
                    au.userid = userid
                    session.add(au)
                    await session.commit()

        # Step 6: Issue JWT
        token = create_token(userid=userid, name=name, mobile=mobile)
        return LoginResponse(
            token=token,
            user=UserInfo(
                userid=userid,
                name=name,
                mobile=mobile,
                avatar=avatar,
                isAdmin=is_admin,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("DingTalk login failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DingTalk login failed: {e}",
        )


@router.get("/me", response_model=UserInfo)
async def get_me(user=Depends(get_current_user)):
    """Get current authenticated user info."""
    mobile = user.get("mobile", "")
    admin_phones = _get_admin_phones()
    is_admin = mobile in admin_phones

    # Try to get fresh info from DB
    avatar = None
    name = user.get("name", "")
    userid = user.get("userid", "")

    async with async_session() as session:
        if userid:
            result = await session.execute(
                select(Employee).where(Employee.userid == userid)
            )
        else:
            result = await session.execute(
                select(Employee).where(Employee.mobile == mobile)
            )
        emp = result.scalar_one_or_none()
        if emp:
            avatar = emp.avatar
            name = emp.name

    return UserInfo(
        userid=userid or None,
        name=name,
        mobile=mobile,
        avatar=avatar,
        isAdmin=is_admin,
    )
