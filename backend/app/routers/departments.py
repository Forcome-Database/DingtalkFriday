"""
Department API router.

GET /api/departments?parentId=1
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.auth import get_current_user
from app.database import async_session
from app.models import Department
from app.schemas import DepartmentOut
from app.config import settings
from app.dingtalk import department as dept_api

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["departments"])


@router.get("/departments", response_model=List[DepartmentOut])
async def get_departments(
    parentId: Optional[int] = Query(default=None, description="Parent department ID"),
    _user=Depends(get_current_user),
):
    """
    Get sub-departments for the given parent department.
    Reads from local DB first; if no data exists, syncs from DingTalk.
    """
    parent_id = parentId if parentId is not None else settings.root_dept_id

    async with async_session() as session:
        result = await session.execute(
            select(Department).where(Department.parent_id == parent_id)
        )
        departments = result.scalars().all()

    # If no departments found locally, try syncing from DingTalk
    if not departments:
        try:
            sub_depts = await dept_api.get_sub_departments(parent_id)
            if sub_depts:
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                from datetime import datetime, timezone

                for dept in sub_depts:
                    async with async_session() as session:
                        stmt = sqlite_insert(Department).values(
                            dept_id=dept["dept_id"],
                            name=dept["name"],
                            parent_id=dept["parent_id"],
                            updated_at=datetime.now(timezone.utc),
                        ).on_conflict_do_update(
                            index_elements=["dept_id"],
                            set_={
                                "name": dept["name"],
                                "parent_id": dept["parent_id"],
                                "updated_at": datetime.now(timezone.utc),
                            },
                        )
                        await session.execute(stmt)
                        await session.commit()

                # Re-query
                async with async_session() as session:
                    result = await session.execute(
                        select(Department).where(Department.parent_id == parent_id)
                    )
                    departments = result.scalars().all()
        except Exception as e:
            logger.warning("Failed to sync departments from DingTalk: %s", e)

    # Determine which departments have children
    dept_ids = [d.dept_id for d in departments]
    children_map = {}
    if dept_ids:
        async with async_session() as session:
            for did in dept_ids:
                result = await session.execute(
                    select(Department.dept_id).where(Department.parent_id == did).limit(1)
                )
                children_map[did] = result.scalar_one_or_none() is not None

    return [
        DepartmentOut(
            dept_id=d.dept_id,
            name=d.name,
            parent_id=d.parent_id,
            hasChildren=children_map.get(d.dept_id, False),
        )
        for d in departments
    ]
