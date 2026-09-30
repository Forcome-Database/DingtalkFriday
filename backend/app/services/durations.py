"""Allocate source durations to business dates without changing their totals."""

import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))
STANDARD_HOURS_PER_DAY = 8.0


def business_today() -> date:
    return datetime.now(BUSINESS_TIMEZONE).date()


def allocate_hours_by_date(
    start: datetime,
    end: datetime,
    total_hours: float,
    *,
    calendar_days: bool = False,
    is_workday: Optional[Callable[[date], bool]] = None,
    day_unit: bool = False,
) -> Dict[date, float]:
    """Split known source hours using day boundaries as relative weights.

    DAY approvals use half-day boundaries; HOUR approvals use the existing
    09:00-12:00 and 13:00-18:00 windows. The source duration remains authoritative
    because these windows do not represent every employee's actual schedule.
    """
    if not math.isfinite(total_hours) or total_hours < 0:
        raise ValueError("Source duration must be finite and non-negative")
    if end < start:
        raise ValueError("Approval end must not precede start")
    if total_hours == 0:
        return {}
    if end == start:
        raise ValueError("Positive duration requires a non-empty approval range")

    last_date = end.date() - timedelta(days=1) if end.time() == time.min else end.date()
    first_date = start.date()
    workday = is_workday or (lambda value: value.weekday() < 5)
    covered_dates = []
    weights = {}
    current = first_date
    while current <= last_date:
        covered_dates.append(current)
        if calendar_days or workday(current):
            if first_date == last_date:
                weight = STANDARD_HOURS_PER_DAY
            elif day_unit:
                weight = STANDARD_HOURS_PER_DAY
                if current == first_date and start.time() >= time(12):
                    weight /= 2
                if current == last_date and time.min < end.time() <= time(13, 30):
                    weight /= 2
            else:
                weight = 0.0
                for window_start, window_end in ((time(9), time(12)), (time(13), time(18))):
                    begin = max(start, datetime.combine(current, window_start, start.tzinfo))
                    finish = min(end, datetime.combine(current, window_end, start.tzinfo))
                    weight += max(0.0, (finish - begin).total_seconds() / 3600)
            if weight > 0:
                weights[current] = weight
        current += timedelta(days=1)

    if not weights:
        # A positive source quota may belong to an unmodelled shift or weekend.
        logger.warning("Duration rule conflict: no calendar/window weights for %s - %s; preserving %.4f source hours", start, end, total_hours)
        weights = {day: 1.0 for day in covered_dates}

    weight_total = math.fsum(weights.values())
    allocation = {day: total_hours * weight / weight_total for day, weight in weights.items()}
    last_day = next(reversed(allocation))
    allocation[last_day] = total_hours - math.fsum(value for day, value in allocation.items() if day != last_day)
    return allocation
