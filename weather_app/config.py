# Configuration and environment lookups.

from __future__ import annotations

import os


DEFAULT_UNITS = "imperial"  # "imperial" or "metric"
DEFAULT_HOURLY_COUNT = 8  # 8 x 3-hour blocks ~= next 24 hours
DEFAULT_DAILY_COUNT = 5


class ConfigError(RuntimeError):
    pass


def get_api_key() -> str:
    # Return the OpenWeatherMap API key from env var.
    key = (os.getenv("OPENWEATHER_API_KEY") or "").strip()
    if not key:
        raise ConfigError(
            "Missing OPENWEATHER_API_KEY. Set it in your environment, e.g.\n"
            'export OPENWEATHER_API_KEY="YOUR_KEY_HERE"'
        )
    return key

