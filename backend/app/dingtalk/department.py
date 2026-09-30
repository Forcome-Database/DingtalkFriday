"""
DingTalk Department API wrappers.
"""

import logging
from typing import Any, Dict, List

from app.dingtalk.client import dingtalk_client

logger = logging.getLogger(__name__)


async def get_department(dept_id: int) -> Dict[str, Any]:
    """
    Get department detail by ID.

    POST /topapi/v2/department/get
    Body: { dept_id, language: "zh_CN" }
    Returns: { dept_id, name, parent_id, ... }
    """
    data = await dingtalk_client.post(
        "/topapi/v2/department/get",
        json_body={"dept_id": dept_id, "language": "zh_CN"},
    )
    result = data.get("result")
    if not isinstance(result, dict) or result.get("dept_id") != dept_id or not result.get("name"):
        raise ValueError("Malformed DingTalk department detail")
    return {
        "dept_id": result.get("dept_id"),
        "name": result.get("name", ""),
        "parent_id": result.get("parent_id", 0),
    }


async def get_sub_departments(dept_id: int = 1) -> List[Dict[str, Any]]:
    """
    Get sub-department list for the given parent department.

    POST /topapi/v2/department/listsub
    Body: { dept_id, language: "zh_CN" }
    Returns: list of { dept_id, name, parent_id }
    """
    data = await dingtalk_client.post(
        "/topapi/v2/department/listsub",
        json_body={"dept_id": dept_id, "language": "zh_CN"},
    )
    result = data.get("result")
    if not isinstance(result, list):
        raise ValueError("Malformed DingTalk sub-department list")
    departments = []
    for item in result:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("dept_id"), int)
            or item["dept_id"] <= 0
            or not item.get("name")
            or item.get("parent_id") != dept_id
        ):
            raise ValueError("Malformed DingTalk sub-department")
        departments.append({
            "dept_id": item.get("dept_id"),
            "name": item.get("name"),
            "parent_id": item.get("parent_id"),
        })
    logger.info("Fetched %d sub-departments for dept_id=%d", len(departments), dept_id)
    return departments


async def get_sub_department_ids(dept_id: int) -> List[int]:
    """
    Get sub-department ID list for the given parent department.

    POST /topapi/v2/department/listsubid
    Body: { dept_id }
    Returns: list of dept_id integers
    """
    data = await dingtalk_client.post(
        "/topapi/v2/department/listsubid",
        json_body={"dept_id": dept_id},
    )
    result = data.get("result", {})
    dept_id_list = result.get("dept_id_list", [])
    logger.info("Fetched %d sub-department IDs for dept_id=%d", len(dept_id_list), dept_id)
    return dept_id_list
