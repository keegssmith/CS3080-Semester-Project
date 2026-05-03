"""OpenWeatherMap API client + forecast aggregation.

- Geocoding (city -> lat/lon)
- Current weather
- 5 day / 3 hour forecast (we treat these as "hourly blocks" and derive a daily view)
"""

from __future__ import annotations
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from typing import Any
import requests
from .config import ConfigError, get_api_key
from .models import CurrentConditions, DailySummary, ForecastEntry, Location


class WeatherApiError(RuntimeError):
    # Raised for network/API/shape issues (non-config).
    pass


class OpenWeatherMapClient:
    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self._timeout_s = timeout_s
        self._session = requests.Session()

    def geocode_city(self, city: str, limit: int = 5) -> list[Location]:
        # Return possible location matches for a user-entered city name.
        city = city.strip()
        if not city:
            raise WeatherApiError("City name cannot be empty.")

        data = self._get_json(
            "https://api.openweathermap.org/geo/1.0/direct",
            {"q": city, "limit": limit, "appid": get_api_key()},
        )
        if not isinstance(data, list):
            raise WeatherApiError("Unexpected response from geocoding API.")

        locations = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            try:
                locations.append(
                    Location(
                        name=name,
                        country=str(item["country"]).strip()
                        if item.get("country")
                        else None,
                        state=str(item["state"]).strip() if item.get("state") else None,
                        lat=float(item["lat"]),
                        lon=float(item["lon"]),
                    )
                )
            except Exception:
                continue
        return locations

    def get_current(
        self, loc: Location, *, units: str
    ) -> tuple[CurrentConditions, int]:
        # Fetch current conditions and return (conditions, timezone_offset_seconds).
        data = self._get_json(
            "https://api.openweathermap.org/data/2.5/weather",
            {"lat": loc.lat, "lon": loc.lon, "units": units, "appid": get_api_key()},
        )

        main = _expect_dict(data, "main")
        weather = _first_weather(data)
        wind = data.get("wind") if isinstance(data, dict) else {}
        tz_offset = int(data.get("timezone") or 0) if isinstance(data, dict) else 0

        return CurrentConditions(
            location_name=loc.display_name,
            temperature=float(main["temp"]),
            feels_like=float(main["feels_like"])
            if main.get("feels_like") is not None
            else None,
            humidity=int(main["humidity"])
            if main.get("humidity") is not None
            else None,
            wind_speed=float(wind["speed"])
            if isinstance(wind, dict) and wind.get("speed") is not None
            else None,
            status=str(weather.get("description") or "Unknown").title(),
            icon=str(weather["icon"]) if weather.get("icon") else None,
        ), tz_offset

    def get_forecast(
        self, loc: Location, *, units: str
    ) -> tuple[list[ForecastEntry], int]:
        # Fetch 5-day/3-hour forecast and return (entries, timezone_offset_seconds).
        data = self._get_json(
            "https://api.openweathermap.org/data/2.5/forecast",
            {"lat": loc.lat, "lon": loc.lon, "units": units, "appid": get_api_key()},
        )

        city = _expect_dict(data, "city")
        tz_offset = int(city.get("timezone") or 0)

        entries = []
        for item in _expect_list(data, "list"):
            if not isinstance(item, dict):
                continue
            dt = item.get("dt")
            main = item.get("main") if isinstance(item.get("main"), dict) else {}
            weather = _first_weather(item)
            if dt is None or not main or main.get("temp") is None:
                continue
            try:
                entries.append(
                    ForecastEntry.from_unix(
                        int(dt),
                        float(main["temp"]),
                        str(weather.get("description") or "Unknown").title(),
                        str(weather["icon"]) if weather.get("icon") else None,
                    )
                )
            except Exception:
                continue

        if not entries:
            raise WeatherApiError("No forecast data returned.")
        return entries, tz_offset

    def build_daily_summaries(
        self, entries: list[ForecastEntry], *, timezone_offset_s: int, days: int
    ) -> list[DailySummary]:
        # Derive daily min/max + dominant condition from 3-hour forecast blocks.
        tz = timezone(timedelta(seconds=timezone_offset_s))

        buckets: dict[str, list[ForecastEntry]] = defaultdict(list)
        for e in entries:
            buckets[e.utc_dt.astimezone(tz).date().isoformat()].append(e)

        summaries = []
        for date in sorted(buckets)[:days]:
            bucket = buckets[date]
            temps = [e.temperature for e in bucket]
            status = Counter(e.status for e in bucket).most_common(1)[0][0]
            icons = Counter(e.icon for e in bucket if e.icon).most_common(1)
            summaries.append(
                DailySummary(
                    date_local=date,
                    temp_min=min(temps),
                    temp_max=max(temps),
                    status=status,
                    icon=icons[0][0] if icons else None,
                )
            )
        return summaries

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout_s)
        except requests.RequestException as e:
            raise WeatherApiError(f"Network error: {e}") from e

        try:
            data = resp.json()
        except ValueError as e:
            raise WeatherApiError("OpenWeatherMap returned a non-JSON response.") from e

        if resp.status_code == 401:
            raise ConfigError("Invalid API key (401 Unauthorized).")
        if resp.status_code == 404:
            raise WeatherApiError("Location not found (404).")
        if resp.status_code == 429:
            raise WeatherApiError("Rate limited by OpenWeatherMap. Try again later.")
        if resp.status_code >= 400:
            msg = data.get("message") if isinstance(data, dict) else None
            raise WeatherApiError(
                f"OpenWeatherMap error ({resp.status_code}): {msg or 'Request failed'}"
            )

        return data


def _expect_dict(data: Any, key: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WeatherApiError("Unexpected response shape.")
    val = data.get(key)
    if not isinstance(val, dict):
        raise WeatherApiError(f"Unexpected response shape: missing '{key}'.")
    return val


def _expect_list(data: Any, key: str) -> list[Any]:
    if not isinstance(data, dict):
        raise WeatherApiError("Unexpected response shape.")
    val = data.get(key)
    if not isinstance(val, list):
        raise WeatherApiError(f"Unexpected response shape: missing '{key}'.")
    return val


def _first_weather(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    weather = data.get("weather")
    if not isinstance(weather, list) or not weather:
        return {}
    first = weather[0]
    return first if isinstance(first, dict) else {}
