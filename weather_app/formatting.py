# Formatting helpers for consistent CLI/GUI display.

from __future__ import annotations

from datetime import timedelta, timezone

from .models import ForecastEntry


def format_temp(value: float, *, units: str) -> str:
    if units == "metric":
        return f"{value:.0f}°C"
    return f"{value:.0f}°F"


def format_local_time(entry: ForecastEntry, *, timezone_offset_s: int) -> str:
    tz = timezone(timedelta(seconds=timezone_offset_s))
    return entry.utc_dt.astimezone(tz).strftime("%a %I:%M %p").lstrip("0")

