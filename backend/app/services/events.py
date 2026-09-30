"""DingTalk Stream inbox, scope discovery, and retryable targeted refreshes."""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta

import httpx
import websockets
from dingtalk_stream import AckMessage, Credential, DingTalkStreamClient, EventHandler
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.database import async_session
from app.dingtalk.client import DingTalkClientError, dingtalk_client
from app.event_models import ApprovalScope, AttendanceRefresh, EventInbox
from app.models import Employee, LeaveRecord, TripRecord
from app.services.durations import BUSINESS_TIMEZONE, business_today

logger = logging.getLogger(__name__)
_sdk_logger = logging.getLogger("app.stream_transport")
_sdk_logger.disabled = True  # SDK logs include connection tickets and raw event bodies.
_stream = None
_tasks = []
_connected_since = None
_connection_gap = True
_gap_generation = 0
_detail_retry_at = datetime.min
_detail_access = None


def _now():
    return datetime.utcnow()


class InboxHandler(EventHandler):
    def __init__(self):
        super().__init__()
        self.logger = _sdk_logger

    async def process(self, event):
        event_id = event.headers.event_id or event.headers.message_id
        if not event_id:
            return AckMessage.STATUS_SYSTEM_EXCEPTION, "Missing event ID"
        now = _now()
        async with async_session() as session:
            await session.execute(sqlite_insert(EventInbox).values(
                event_id=event_id, event_type=event.headers.event_type or "unknown",
                payload=json.dumps(event.data, ensure_ascii=True), received_at=now,
                next_attempt_at=now, attempts=0,
            ).on_conflict_do_nothing(index_elements=["event_id"]))
            await session.commit()
        return AckMessage.STATUS_OK, "OK"


class AsyncStreamClient(DingTalkStreamClient):
    """Use SDK routing with cancellable I/O and a bounded connection timeout."""

    async def start(self):
        global _connected_since, _connection_gap, _gap_generation
        self.pre_start()
        disconnected_at = _now()
        async with httpx.AsyncClient(timeout=30) as http:
            while True:
                try:
                    response = await http.post(self.OPEN_CONNECTION_API, json={
                        "clientId": self.credential.client_id,
                        "clientSecret": self.credential.client_secret,
                        "subscriptions": [{"type": "EVENT", "topic": "*"}],
                        "ua": "DingtalkFriday/1.0",
                    })
                    response.raise_for_status()
                    connection = response.json()
                    from urllib.parse import quote_plus
                    uri = connection["endpoint"] + "?ticket=" + quote_plus(connection["ticket"])
                    async with websockets.connect(uri, ping_interval=30, ping_timeout=30) as ws:
                        self.websocket = ws
                        if disconnected_at and (_now() - disconnected_at).total_seconds() > 60:
                            _connection_gap = True
                        disconnected_at = None
                        _connected_since = _now()
                        logger.info("DingTalk Stream connected")
                        async for message in ws:
                            result = await self.route_message(json.loads(message))
                            if result == self.TAG_DISCONNECT:
                                break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("DingTalk Stream disconnected: %s", type(exc).__name__)
                finally:
                    self.websocket = None
                    _connected_since = None
                    if disconnected_at is None:
                        disconnected_at = _now()
                        _gap_generation += 1
                await asyncio.sleep(10)


def _date_value(value):
    if isinstance(value, (int, float)):
        if value < 946684800000:
            return None
        return datetime.fromtimestamp(value / 1000, BUSINESS_TIMEZONE).date()
    if not isinstance(value, str):
        return None
    if value.endswith((" \u4e0a\u5348", " \u4e0b\u5348")):
        value = value.split(" ", 1)[0]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(BUSINESS_TIMEZONE)
        return parsed.date()
    except ValueError:
        return None


def form_dates(detail):
    """Decode structured date ranges; avoid mistaking form durations for dates."""
    dates = set()

    def visit(value):
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                return
            if isinstance(decoded, (dict, list)):
                visit(decoded)
            return
        if isinstance(value, dict):
            start = next((_date_value(value[k]) for k in ("start", "startTime", "beginTime", "begin_time", "start_time", "_from")
                          if k in value and _date_value(value[k])), None)
            end = next((_date_value(value[k]) for k in ("end", "endTime", "end_time", "finish_time", "_to")
                        if k in value and _date_value(value[k])), None)
            if start and end:
                add_range(start, end)
            for child in value.values():
                if isinstance(child, (dict, list)) or isinstance(child, str) and child[:1] in {"[", "{"}:
                    visit(child)
        elif isinstance(value, list):
            if len(value) >= 2:
                start, end = _date_value(value[0]), _date_value(value[1])
                if start and end:
                    add_range(start, end)
            for child in value:
                visit(child)

    def add_range(start, end):
        if end < start or (end - start).days > 3660:
            raise ValueError("Invalid approval date range")
        dates.update((start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1))

    for form in detail.get("formComponentValues", detail.get("form_component_values", [])):
        visit(form.get("value"))
        visit(form.get("extValue"))
    return dates


async def _enqueue(session, domain, userid, date_key):
    values = dict(domain=domain, userid=userid, date_key=str(date_key), attempts=0,
                  error=None, next_attempt_at=_now())
    await session.execute(sqlite_insert(AttendanceRefresh).values(**values).on_conflict_do_update(
        index_elements=["domain", "userid", "date_key"], set_=values,
    ))


async def _approval_event(payload):
    global _detail_access, _detail_retry_at
    instance_id = payload.get("processInstanceId", payload.get("process_instance_id"))
    if not instance_id:
        raise ValueError("Approval event missing instance ID")
    async with async_session() as session:
        old_scope = await session.get(ApprovalScope, instance_id)
        old_rows = (await session.execute(select(TripRecord).where(
            TripRecord.proc_inst_id == instance_id
        ))).scalars().all()
    detail_unavailable = _detail_access is False and _now() < _detail_retry_at
    try:
        detail = {} if detail_unavailable else await dingtalk_client.workflow_instance(instance_id)
        if not detail_unavailable:
            _detail_access = True
    except DingTalkClientError as exc:
        if exc.errcode == 403:
            _detail_access = False
            _detail_retry_at = _now() + timedelta(minutes=1)
            detail_unavailable = True
            detail = {}
            logger.warning("Workflow.Instance.Read unavailable; refreshing employee attendance scope")
        elif payload.get("type") == "delete":
            detail = {}
        else:
            raise
    userid = (detail.get("originatorUserId") or detail.get("originator_userid")
              or payload.get("staffId") or (old_scope.userid if old_scope else None)
              or (old_rows[0].userid if old_rows else None))
    if not userid:
        raise ValueError("Cannot resolve approval employee")
    old_dates = set(json.loads(old_scope.dates)) if old_scope else set()
    old_dates.update(row.work_date for row in old_rows)
    new_dates = form_dates(detail)
    if detail_unavailable:
        async with async_session() as session:
            historical_dates = (await session.execute(select(TripRecord.work_date).where(
                TripRecord.userid == userid
            ).distinct())).scalars().all()
        old_dates.update(historical_dates)
        first = business_today() - timedelta(days=settings.trip_hot_days_past)
        last = business_today() + timedelta(days=max(settings.trip_hot_days_future, settings.trip_warm_days_future))
        new_dates.update((first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1))
    attached = detail.get("attachedProcessInstanceIds", detail.get("attached_process_instance_ids", [])) or []
    action = str(detail.get("bizAction", detail.get("biz_action", ""))).upper()
    changed_parents = []
    if action in {"REVOKE", "MODIFY"} and detail.get("status") == "COMPLETED" and detail.get("result") == "agree":
        async with async_session() as session:
            candidates = (await session.execute(select(ApprovalScope).where(
                ApprovalScope.userid == userid
            ))).scalars().all()
            known_ids = (await session.execute(select(TripRecord.proc_inst_id).where(
                TripRecord.userid == userid
            ).distinct())).scalars().all()
        for scope in candidates:
            if instance_id in json.loads(scope.attached_ids):
                changed_parents.append(scope.instance_id)
                old_dates.update(json.loads(scope.dates))
        # An original approval may predate Stream. Discover its attachment once on change.
        if not changed_parents:
            for parent_id in known_ids:
                if parent_id == instance_id:
                    continue
                parent = await dingtalk_client.workflow_instance(parent_id)
                children = parent.get("attachedProcessInstanceIds", parent.get("attached_process_instance_ids", [])) or []
                if instance_id in children:
                    changed_parents.append(parent_id)
                    old_dates.update(form_dates(parent))
    all_dates = old_dates | new_dates
    # Unknown form layouts retain all previously covered employee dates.
    if not new_dates and not detail_unavailable:
        first = business_today() - timedelta(days=settings.trip_hot_days_past)
        last = business_today() + timedelta(days=max(settings.trip_hot_days_future, settings.trip_warm_days_future))
        all_dates.update((first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1))
        async with async_session() as session:
            all_dates.update((await session.execute(select(TripRecord.work_date).where(
                TripRecord.userid == userid
            ).distinct())).scalars().all())
    years = {date.fromisoformat(day).year for day in all_dates} or {business_today().year}
    now = _now()
    async with async_session() as session:
        if await session.get(Employee, userid) is None:
            from app.services.sync import sync_departments, sync_employees
            await sync_departments()
            await sync_employees()
            if await session.get(Employee, userid) is None:
                # An approval outside the configured organization does not change its inventory.
                return
        for year in years:
            await _enqueue(session, "leave", userid, year)
        for day in all_dates:
            await _enqueue(session, "trip", userid, day)
        if detail.get("status") == "TERMINATED" or payload.get("type") in {"terminate", "delete"}:
            await session.execute(delete(TripRecord).where(TripRecord.proc_inst_id == instance_id))
        for parent_id in changed_parents:
            await session.execute(delete(TripRecord).where(TripRecord.proc_inst_id == parent_id))
            parent_values = dict(instance_id=parent_id, userid=userid, dates=json.dumps(sorted(old_dates)),
                                 attached_ids=json.dumps([instance_id]), status="REVOKED" if action == "REVOKE" else "REPLACED",
                                 updated_at=now)
            await session.execute(sqlite_insert(ApprovalScope).values(**parent_values).on_conflict_do_update(
                index_elements=["instance_id"], set_=parent_values,
            ))
        final_status = "DELETED" if payload.get("type") == "delete" else detail.get("status")
        if payload.get("type") == "terminate":
            final_status = "TERMINATED"
        if old_scope and old_scope.status in {"TERMINATED", "REVOKED", "REPLACED", "DELETED"}:
            final_status = old_scope.status
        values = dict(instance_id=instance_id, userid=userid, dates=json.dumps(sorted(new_dates or old_dates)),
                      attached_ids=json.dumps(attached), status=final_status,
                      result=detail.get("result"), updated_at=now)
        await session.execute(sqlite_insert(ApprovalScope).values(**values).on_conflict_do_update(
            index_elements=["instance_id"], set_=values,
        ))
        # Attachments encode modifications/revocations and may refer to a different date range.
        visited = set(payload.get("_visited_instances", [])) | {instance_id}
        if len(visited) > 30:
            raise ValueError("Too many attached approval instances")
        for attachment in attached:
            if attachment in visited:
                continue
            await session.execute(sqlite_insert(EventInbox).values(
                event_id=f"attachment:{instance_id}:{attachment}:{payload.get('finishTime', payload.get('createTime', now.isoformat()))}",
                event_type="bpms_instance_change", payload=json.dumps({"processInstanceId": attachment, "staffId": userid,
                                                                        "_visited_instances": sorted(visited)}),
                received_at=now, next_attempt_at=now, attempts=0,
            ).on_conflict_do_nothing(index_elements=["event_id"]))
        await session.commit()


async def process_events():
    now = _now()
    async with async_session() as session:
        rows = (await session.execute(select(EventInbox).where(
            EventInbox.processed_at.is_(None), EventInbox.next_attempt_at <= now,
        ).order_by(EventInbox.received_at).limit(100))).scalars().all()
    groups = {}
    for row in rows:
        payload = json.loads(row.payload)
        key = (("organization", "organization") if row.event_type.startswith(("user_", "org_dept_", "org_admin_"))
               else (row.event_type, payload.get("processInstanceId", "organization")))
        groups.setdefault(key, []).append((row, payload))
    for (event_type, _), group in groups.items():
        error = None
        try:
            if event_type == "bpms_instance_change":
                payload = dict(group[-1][1])
                terminal = {item.get("type") for _, item in group} & {"delete", "terminate"}
                if terminal:
                    payload["type"] = "delete" if "delete" in terminal else "terminate"
                if not payload.get("staffId"):
                    payload["staffId"] = next((item["staffId"] for _, item in reversed(group) if item.get("staffId")), None)
                await _approval_event(payload)
            elif event_type == "organization":
                from app.services.sync import sync_departments, sync_employees
                await sync_departments()
                await sync_employees()
            elif event_type == "attend_bossCheck_change":
                async with async_session() as session:
                    for _, payload in group:
                        uid = payload.get("userId")
                        day = _date_value(payload.get("workDate"))
                        if not uid or not day:
                            raise ValueError("Invalid attendance change scope")
                        await _enqueue(session, "trip", uid, day.isoformat())
                        await _enqueue(session, "leave", uid, day.year)
                    await session.commit()
        except Exception as exc:
            error = type(exc).__name__
            logger.warning("Event processing failed (%s): %s", event_type, error)
        async with async_session() as session:
            for row, _ in group:
                item = await session.get(EventInbox, row.event_id)
                if error:
                    item.attempts += 1
                    item.error = error
                    item.next_attempt_at = now + timedelta(seconds=min(3600, 10 * 2 ** min(item.attempts, 9)))
                else:
                    item.processed_at = _now()
                    item.error = None
            await session.commit()


async def process_refreshes():
    from app.services.sync import is_full_sync_running, refresh_leave_records
    from app.services.trip_sync import _sync_one, is_trip_sync_running
    if is_full_sync_running() or is_trip_sync_running():
        return
    async with async_session() as session:
        rows = (await session.execute(select(AttendanceRefresh).where(
            AttendanceRefresh.next_attempt_at <= _now(),
        ).order_by(AttendanceRefresh.next_attempt_at).limit(100))).scalars().all()
    for row in rows:
        try:
            if row.domain == "leave":
                await refresh_leave_records(row.userid, int(row.date_key))
            else:
                await _sync_one(row.userid, row.date_key, asyncio.Semaphore(1), require_settled=True)
        except Exception as exc:
            async with async_session() as session:
                item = await session.get(AttendanceRefresh, (row.domain, row.userid, row.date_key))
                item.attempts += 1
                item.error = type(exc).__name__
                item.next_attempt_at = _now() + timedelta(seconds=min(3600, 10 * 2 ** min(item.attempts, 9)))
                await session.commit()
            logger.warning("Targeted refresh failed: %s", type(exc).__name__)
        else:
            async with async_session() as session:
                await session.execute(delete(AttendanceRefresh).where(
                    AttendanceRefresh.domain == row.domain, AttendanceRefresh.userid == row.userid,
                    AttendanceRefresh.date_key == row.date_key,
                ))
                await session.commit()


async def _worker():
    conflicts_checked_at = datetime.min
    while True:
        try:
            if (_now() - conflicts_checked_at).total_seconds() >= 3600:
                await _queue_leave_conflicts()
                conflicts_checked_at = _now()
            await process_events()
            await process_refreshes()
            async with async_session() as session:
                await session.execute(delete(EventInbox).where(
                    EventInbox.processed_at < _now() - timedelta(days=90),
                ))
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Event worker failed: %s", type(exc).__name__)
        await asyncio.sleep(max(1, settings.event_poll_seconds))


async def _queue_leave_conflicts():
    async with async_session() as session:
        pending = (await session.execute(select(LeaveRecord).where(
            LeaveRecord.status == "\u5f85\u590d\u6838",
        ))).scalars().all()
        pairs = set()
        for record in pending:
            first = datetime.fromtimestamp(record.start_time / 1000, BUSINESS_TIMEZONE).year
            last = datetime.fromtimestamp(record.end_time / 1000, BUSINESS_TIMEZONE).year
            pairs.update((record.userid, year) for year in range(first, last + 1))
        for userid, year in pairs:
            await session.execute(sqlite_insert(AttendanceRefresh).values(
                domain="leave", userid=userid, date_key=str(year), attempts=0,
                next_attempt_at=_now(),
            ).on_conflict_do_nothing(index_elements=["domain", "userid", "date_key"]))
        await session.commit()


async def event_status():
    async with async_session() as session:
        pending = (await session.execute(select(func.count()).select_from(EventInbox).where(
            EventInbox.processed_at.is_(None)
        ))).scalar_one()
        refreshes = (await session.execute(select(func.count()).select_from(AttendanceRefresh))).scalar_one()
        failures = (await session.execute(select(func.count()).select_from(EventInbox).where(
            EventInbox.processed_at.is_(None), EventInbox.attempts > 0,
        ))).scalar_one()
        received, processed = (await session.execute(select(
            func.max(EventInbox.received_at), func.max(EventInbox.processed_at)
        ))).one()
    return dict(enabled=settings.dingtalk_stream_enabled,
                connected=bool(_stream and _stream.websocket is not None),
                compensation_optimized=settings.dingtalk_stream_compensation_enabled,
                workflow_detail_access=_detail_access,
                scope_resolution="employee_fallback" if _detail_access is False else "approval",
                pending_events=pending, pending_refreshes=refreshes, failed_events=failures,
                last_received_at=received, last_processed_at=processed)


async def start_event_service():
    global _stream
    if not settings.dingtalk_stream_enabled:
        return
    _stream = AsyncStreamClient(Credential(settings.dingtalk_app_key, settings.dingtalk_app_secret), logger=_sdk_logger)
    _stream.system_handler.logger = _sdk_logger
    _stream.register_all_event_handler(InboxHandler())
    _tasks.extend([asyncio.create_task(_stream.start()), asyncio.create_task(_worker())])


async def stop_event_service():
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()


def trip_coverage_epoch():
    return _gap_generation


def mark_trip_coverage_complete(epoch):
    global _connection_gap
    if epoch != _gap_generation:
        _connection_gap = True
        return
    if _stream and _stream.websocket is not None and epoch == _gap_generation:
        _connection_gap = False


async def compensate_trip_sync():
    """Retain daily full coverage until verified event compensation is enabled."""
    global _connection_gap
    from app.services.trip_sync import is_trip_sync_running, sync_trip_records, _sync_one
    status = await event_status()
    if is_trip_sync_running():
        return "Trip sync already running"
    if not settings.dingtalk_stream_compensation_enabled:
        return await sync_trip_records(recover_gap=not status["connected"] or _connection_gap)
    if not status["connected"] or _connection_gap or business_today().weekday() == 0:
        return await sync_trip_records(recover_gap=True)
    first = (business_today() - timedelta(days=settings.trip_hot_days_past)).isoformat()
    last = (business_today() + timedelta(days=settings.trip_warm_days_future)).isoformat()
    async with async_session() as session:
        pairs = (await session.execute(select(TripRecord.userid, TripRecord.work_date).where(
            TripRecord.work_date >= first, TripRecord.work_date <= last,
        ).distinct())).all()
        for userid, work_date in pairs:
            await _enqueue(session, "trip", userid, work_date)
        await session.commit()
    logger.info("Trip compensation queued %d known employee dates", len(pairs))
    return f"Queued {len(pairs)} known trip dates"
