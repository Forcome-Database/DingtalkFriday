"""
DingTalk User API wrappers.
"""

import logging
from typing import Any, Dict, List

from app.dingtalk.client import dingtalk_client

logger = logging.getLogger(__name__)


async def get_user_list_simple(dept_id: int) -> List[Dict[str, Any]]:
    """
    Get a simple user list (userid + name) for a department.
    Handles cursor-based pagination automatically.

    POST /topapi/user/listsimple
    Body: { dept_id, cursor: 0, size: 100 }
    Returns: list of { userid, name }
    """
    users: List[Dict[str, Any]] = []
    cursor = 0
    size = 100

    while True:
        data = await dingtalk_client.post(
            "/topapi/user/listsimple",
            json_body={"dept_id": dept_id, "cursor": cursor, "size": size},
        )
        result = data.get("result", {})
        page_list = result.get("list", [])

        for item in page_list:
            users.append({
                "userid": item.get("userid"),
                "name": item.get("name"),
            })

        has_more = result.get("has_more", False)
        if has_more:
            cursor = result.get("next_cursor", 0)
        else:
            break

    logger.info("Fetched %d users for dept_id=%d", len(users), dept_id)
    return users


async def get_user_id_list(dept_id: int) -> List[str]:
    """
    Get a list of user IDs for a department.

    POST /topapi/user/listid
    Body: { dept_id }
    Returns: list of userid strings
    """
    data = await dingtalk_client.post(
        "/topapi/user/listid",
        json_body={"dept_id": dept_id},
    )
    result = data.get("result", {})
    userid_list = result.get("userid_list", [])
    logger.info("Fetched %d user IDs for dept_id=%d", len(userid_list), dept_id)
    return userid_list
