from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _opening_time(day):
    if day.weekday() <= 4:
        return day.replace(hour=9, minute=0, second=0, microsecond=0)
    if day.weekday() == 5:
        return day.replace(hour=9, minute=0, second=0, microsecond=0)
    return None


def _closing_time(day):
    if day.weekday() <= 4:
        return day.replace(hour=18, minute=0, second=0, microsecond=0)
    if day.weekday() == 5:
        return day.replace(hour=13, minute=0, second=0, microsecond=0)
    return None


def store_status(timezone_name: str = "America/Campo_Grande", now: datetime | None = None) -> dict:
    tz = ZoneInfo(timezone_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    opening = _opening_time(current)
    closing = _closing_time(current)
    is_open = bool(opening and closing and opening <= current < closing)

    next_opening = None
    for offset in range(0, 8):
        candidate_day = (current + timedelta(days=offset)).date()
        candidate = datetime.combine(candidate_day, datetime.min.time(), tzinfo=tz)
        candidate_open = _opening_time(candidate)
        if candidate_open is None:
            continue
        if candidate_open > current:
            next_opening = candidate_open
            break

    if is_open:
        message = "The store is open now."
    elif next_opening:
        message = (
            "The store is closed now. The next opening is "
            f"{WEEKDAYS[next_opening.weekday()]}, {next_opening.strftime('%d/%m at %H:%M')}."
        )
    else:
        message = "The store is closed now."

    return {
        "local_time": current.isoformat(timespec="minutes"),
        "local_time_br": current.strftime("%d/%m/%Y %H:%M"),
        "weekday": WEEKDAYS[current.weekday()],
        "is_open": is_open,
        "message": message,
        "next_opening": next_opening.isoformat(timespec="minutes") if next_opening else None,
        "next_opening_br": (
            next_opening.strftime("%d/%m/%Y %H:%M") if next_opening else None
        ),
        "hours": {
            "monday_to_friday": "09:00 to 18:00",
            "saturday": "09:00 to 13:00",
            "sunday_and_holidays": "closed",
        },
        "holiday_note": "Holidays are not modeled; Sundays and holidays are treated as closed.",
    }
