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
    seen_cursors = {cursor}
    seen_userids = set()

    while True:
        data = await dingtalk_client.post(
            "/topapi/user/listsimple",
            json_body={"dept_id": dept_id, "cursor": cursor, "size": size},
        )
        result = data.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise ValueError("Malformed DingTalk user list page")
        page_list = result["list"]
        has_more = result.get("has_more")
        if not isinstance(has_more, bool) or (has_more and not page_list):
            raise ValueError("Malformed DingTalk user list pagination")

        for item in page_list:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("userid"), str)
                or not item["userid"]
                or not item.get("name")
                or item["userid"] in seen_userids
            ):
                raise ValueError("Malformed or repeated DingTalk user list record")
            seen_userids.add(item["userid"])
            users.append({
                "userid": item.get("userid"),
                "name": item.get("name"),
            })

        if has_more:
            next_cursor = result.get("next_cursor")
            if not isinstance(next_cursor, int) or next_cursor in seen_cursors:
                raise ValueError("DingTalk user list cursor did not advance")
            cursor = next_cursor
            seen_cursors.add(cursor)
        else:
            break

    logger.info("Fetched %d users for dept_id=%d", len(users), dept_id)
    return users


async def get_user_info_by_code(auth_code: str) -> Dict[str, Any]:
    """
    Exchange a login auth code for basic user info (userid, etc.).

    POST /topapi/v2/user/getuserinfo
    Body: { code }
    Returns: { result: { userid, sys_level, ... } }
    """
    data = await dingtalk_client.post(
        "/topapi/v2/user/getuserinfo",
        json_body={"code": auth_code},
    )
    result = data.get("result", {})
    logger.info("Got user info by auth code: userid=%s", result.get("userid"))
    return result


async def get_user_detail(userid: str) -> Dict[str, Any]:
    """
    Get full user detail by userid.

    POST /topapi/v2/user/get
    Body: { userid }
    Returns: { result: { userid, name, mobile, avatar, ... } }
    """
    data = await dingtalk_client.post(
        "/topapi/v2/user/get",
        json_body={"userid": userid},
    )
    result = data.get("result", {})
    logger.info("Got user detail: userid=%s, name=%s", result.get("userid"), result.get("name"))
    return result


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
