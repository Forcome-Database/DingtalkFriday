"""Shared department utilities used by leave and trip services."""

from typing import Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department


async def get_descendant_dept_ids(session: AsyncSession, dept_id: int) -> Set[int]:
    """Get all descendant department IDs including the given one."""
    result = {dept_id}
    queue = [dept_id]
    while queue:
        parent = queue.pop()
        rows = await session.execute(
            select(Department.dept_id).where(Department.parent_id == parent)
        )
        for (child_id,) in rows:
            if child_id not in result:
                result.add(child_id)
                queue.append(child_id)
    return result
