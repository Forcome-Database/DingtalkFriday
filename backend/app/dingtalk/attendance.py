"""
DingTalk Attendance / Leave API wrappers.
"""

import logging
import json
from typing import Any, Dict, List

from app.dingtalk.client import dingtalk_client

logger = logging.getLogger(__name__)


def _page(data: Dict[str, Any], field: str, seen_pages: set) -> tuple:
    result = data.get("result")
    if not isinstance(result, dict) or not isinstance(result.get(field), list):
        raise ValueError(f"Malformed DingTalk {field} page")
    items = result[field]
    has_more = result.get("has_more")
    if not isinstance(has_more, bool):
        raise ValueError(f"Malformed DingTalk {field} pagination flag")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError(f"Malformed DingTalk {field} record")
    signature = json.dumps(items, sort_keys=True, separators=(",", ":"))
    if items and signature in seen_pages:
        raise ValueError(f"Repeated DingTalk {field} page")
    if has_more and not items:
        raise ValueError(f"Empty DingTalk {field} page with has_more=true")
    seen_pages.add(signature)
    return items, has_more


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"Invalid DingTalk {field}")
    try:
        return int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid DingTalk {field}") from exc


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
    if not userid_list or len(userid_list) > 100 or len(set(userid_list)) != len(userid_list):
        raise ValueError("Leave status requires 1-100 distinct user IDs")
    if not 1 <= size <= 20 or offset < 0:
        raise ValueError("Invalid leave status page size or offset")
    if start_time >= end_time or end_time - start_time > 180 * 86400000:
        raise ValueError("Leave status query must span at most 180 days")
    records: List[Dict[str, Any]] = []
    current_offset = offset
    seen_pages: set = set()

    # Join userids into a comma-separated string (max 100)
    userid_str = ",".join(userid_list)

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
        leave_status, has_more = _page(data, "leave_status", seen_pages)

        for item in leave_status:
            start = _integer(item.get("start_time"), "start_time")
            end = _integer(item.get("end_time"), "end_time")
            duration = _integer(item.get("duration_percent"), "duration_percent")
            if item.get("userid") not in userid_list or end <= start or duration < 0:
                raise ValueError("Invalid DingTalk leave status interval or user")
            if end < start_time or start > end_time:
                raise ValueError("DingTalk leave status falls outside requested interval")
            if item.get("duration_unit") not in {"percent_day", "percent_hour"}:
                raise ValueError("Invalid DingTalk leave duration unit")
            records.append({
                "userid": item.get("userid"),
                "start_time": start,
                "end_time": end,
                "duration_percent": duration,
                "duration_unit": item.get("duration_unit"),
                "leave_code": str(item["leave_code"]) if item.get("leave_code") is not None else None,
                "leave_status": item.get("leave_status"),
            })

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
    size: int = 200,
) -> List[Dict[str, Any]]:
    """
    Query vacation consumption records for specific leave_code and users.
    Handles pagination (has_more) automatically.

    POST /topapi/attendance/vacation/record/list

    Returns: list of {
        userid, leave_code, record_id, start_time, end_time,
        record_num_per_day, record_num_per_hour,
        leave_view_unit, leave_status, cal_type
    }
    Retains all states, including pending applications and reversals,
    so callers can reconcile conflicts without silently dropping them.
    """
    if not userids or len(userids) > 50 or len(set(userids)) != len(userids):
        raise ValueError("Vacation records require 1-50 distinct user IDs")
    if not 1 <= size <= 200 or offset < 0:
        raise ValueError("Invalid vacation record page size or offset")
    records: List[Dict[str, Any]] = []
    current_offset = offset
    seen_pages: set = set()
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
        leave_records, has_more = _page(data, "leave_records", seen_pages)

        for item in leave_records:
            if item.get("userid") not in userids:
                raise ValueError("DingTalk returned vacation record for an unrequested user")
            if item.get("leave_code") is not None and str(item["leave_code"]) != str(leave_code):
                raise ValueError("DingTalk returned vacation record for an unrequested leave type")
            start, end = item.get("start_time"), item.get("end_time")
            if start in (None, 0) and end in (None, 0):
                start, end = None, None
            else:
                start = _integer(start, "vacation start_time")
                end = _integer(end, "vacation end_time")
                if end <= start:
                    raise ValueError("Invalid DingTalk vacation interval")
            records.append({
                "userid": item.get("userid"),
                "leave_code": str(item.get("leave_code") or leave_code),
                "record_id": str(item["record_id"]).strip() if item.get("record_id") is not None else None,
                "start_time": start,
                "end_time": end,
                "record_num_per_day": item.get("record_num_per_day"),
                "record_num_per_hour": item.get("record_num_per_hour"),
                "leave_view_unit": item.get("leave_view_unit"),
                "leave_status": item.get("leave_status"),
                "cal_type": item.get("cal_type"),
                "leave_record_type": item.get("leave_record_type"),
            })

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
    result = data.get("result")
    if not isinstance(result, list):
        raise ValueError("Malformed DingTalk vacation type list")
    types = []
    for item in result:
        if not isinstance(item, dict) or not item.get("leave_code") or not item.get("leave_name"):
            raise ValueError("Malformed DingTalk vacation type")
        types.append({
            "leave_code": str(item.get("leave_code", "")),
            "leave_name": item.get("leave_name", ""),
            "leave_view_unit": item.get("leave_view_unit", ""),
            "hours_in_per_day": item.get("hours_in_per_day", 800),
            "biz_type": item.get("biz_type"),
        })
    logger.info("Fetched %d vacation types", len(types))
    return types


async def get_update_data(userid: str, work_date: str) -> Dict[str, Any]:
    """
    Query a user's attendance data for a specific date.

    POST /topapi/attendance/getupdatedata
    Body: { userid, work_date }

    Returns the full response dict containing:
    - approve_list: list of approval records with biz_type, tag_name, etc.
    - check_record_list: clock-in records
    - attendance_result_list: attendance results
    """
    data = await dingtalk_client.post(
        "/topapi/attendance/getupdatedata",
        json_body={
            "userid": userid,
            "work_date": work_date,
        },
    )
    return data.get("result", {})
