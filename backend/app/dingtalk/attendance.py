"""
DingTalk Attendance / Leave API wrappers.
"""

import logging
from typing import Any, Dict, List

from app.dingtalk.client import dingtalk_client

logger = logging.getLogger(__name__)


async def get_leave_status(
    userid_list: List[str],
    start_time: int,
    end_time: int,
    offset: int = 0,
    size: int = 20,
) -> List[Dict[str, Any]]:
    """
    Query leave status for a batch of users within a time range.
    Handles pagination (has_more) automatically.

    POST /topapi/attendance/getleavestatus
    Body: {
        userid_list: "user1,user2,...",  (max 100 users)
        start_time: unix_ms,
        end_time: unix_ms,
        offset: int,
        size: int (max 20)
    }

    NOTE: The caller is responsible for splitting users into batches of 100.
          The max query time span is 180 days.

    Returns: list of {
        userid, start_time, end_time,
        duration_percent, duration_unit
    }
    """
    records: List[Dict[str, Any]] = []
    current_offset = offset

    # Join userids into a comma-separated string (max 100)
    userid_str = ",".join(userid_list[:100])

    while True:
        data = await dingtalk_client.post(
            "/topapi/attendance/getleavestatus",
            json_body={
                "userid_list": userid_str,
                "start_time": start_time,
                "end_time": end_time,
                "offset": current_offset,
                "size": size,
            },
        )
        result = data.get("result", {})
        leave_status = result.get("leave_status", [])

        for item in leave_status:
            records.append({
                "userid": item.get("userid"),
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
                "duration_percent": item.get("duration_percent"),
                "duration_unit": item.get("duration_unit"),
            })

        has_more = result.get("has_more", False)
        if has_more:
            current_offset += size
        else:
            break

    logger.info(
        "Fetched %d leave records for %d users, time range [%d, %d]",
        len(records), len(userid_list), start_time, end_time,
    )
    return records


async def get_vacation_record_list(
    op_userid: str,
    leave_code: str,
    userids: List[str],
    offset: int = 0,
    size: int = 50,
) -> List[Dict[str, Any]]:
    """
    Query vacation consumption records for specific leave_code and users.
    Handles pagination (has_more) automatically.

    POST /topapi/attendance/vacation/record/list

    Returns: list of {
        userid, leave_code, start_time, end_time,
        record_num_per_day, record_num_per_hour,
        leave_view_unit, leave_status, cal_type
    }
    Only returns records with leave_status='success' and cal_type=null (actual leave).
    """
    records: List[Dict[str, Any]] = []
    current_offset = offset
    userid_str = ",".join(userids)

    while True:
        data = await dingtalk_client.post(
            "/topapi/attendance/vacation/record/list",
            json_body={
                "op_userid": op_userid,
                "leave_code": leave_code,
                "userids": userid_str,
                "offset": current_offset,
                "size": size,
            },
        )
        result = data.get("result", {})
        leave_records = result.get("leave_records", [])

        for item in leave_records:
            # Only keep actual leave records (cal_type=null means leave consumption)
            if item.get("leave_status") != "success":
                continue
            if item.get("cal_type") is not None:
                continue
            records.append({
                "userid": item.get("userid"),
                "leave_code": item.get("leave_code"),
                "start_time": item.get("start_time"),
                "end_time": item.get("end_time"),
                "record_num_per_day": item.get("record_num_per_day"),
                "record_num_per_hour": item.get("record_num_per_hour"),
                "leave_view_unit": item.get("leave_view_unit"),
                "leave_status": item.get("leave_status"),
            })

        has_more = result.get("has_more", False)
        if has_more:
            current_offset += size
        else:
            break

    logger.info(
        "Fetched %d vacation records for leave_code=%s, %d users",
        len(records), leave_code, len(userids),
    )
    return records


async def get_vacation_type_list(op_userid: str) -> List[Dict[str, Any]]:
    """
    Get the list of all vacation (leave) types.

    POST /topapi/attendance/vacation/type/list
    Body: { op_userid, vacation_source: "all" }

    Returns: list of {
        leave_code, leave_name, leave_view_unit,
        hours_in_per_day, biz_type
    }
    """
    data = await dingtalk_client.post(
        "/topapi/attendance/vacation/type/list",
        json_body={
            "op_userid": op_userid,
            "vacation_source": "all",
        },
    )
    result = data.get("result", [])
    types = []
    for item in result:
        types.append({
            "leave_code": str(item.get("leave_code", "")),
            "leave_name": item.get("leave_name", ""),
            "leave_view_unit": item.get("leave_view_unit", ""),
            "hours_in_per_day": item.get("hours_in_per_day", 800),
            "biz_type": item.get("biz_type"),
        })
    logger.info("Fetched %d vacation types", len(types))
    return types
