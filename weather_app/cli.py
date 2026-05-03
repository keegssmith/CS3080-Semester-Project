"""CLI implementation.

Ask for a city, then print:
- current conditions
- next few 3-hour forecast blocks ("hourly")
- daily forecast summaries
"""

from __future__ import annotations
from .config import DEFAULT_DAILY_COUNT, DEFAULT_HOURLY_COUNT, ConfigError
from .formatting import format_local_time, format_temp
from .owm_client import OpenWeatherMapClient, WeatherApiError


def run_cli(*, city: str | None, units: str) -> None:
    if not city:
        city = input("Enter a city: ").strip()

    client = OpenWeatherMapClient()

    try:
        locs = client.geocode_city(city)
        if not locs:
            raise WeatherApiError(f"No matches found for '{city}'.")
        loc = locs[0]

        current, tz_offset_current = client.get_current(loc, units=units)
        forecast_entries, tz_offset_forecast = client.get_forecast(loc, units=units)

        tz_offset = tz_offset_forecast if tz_offset_forecast is not None else tz_offset_current

        hourly = forecast_entries[:DEFAULT_HOURLY_COUNT]
        daily = client.build_daily_summaries(forecast_entries, timezone_offset_s=tz_offset, days=DEFAULT_DAILY_COUNT)

    except (ConfigError, WeatherApiError) as e:
        print(f"\nError: {e}\n")
        return

    print()
    print(f"{current.location_name}")
    print("-" * len(current.location_name))
    print(f"{format_temp(current.temperature, units=units)} • {current.status}")

    details = [
        f"Feels like {format_temp(current.feels_like, units=units)}" if current.feels_like is not None else None,
        f"Humidity {current.humidity}%" if current.humidity is not None else None,
        f"Wind {current.wind_speed:.0f}" if current.wind_speed is not None else None,
    ]
    details_line = " | ".join(d for d in details if d)
    if details_line:
        print(details_line)

    print()
    print("Hourly (3-hour blocks)")
    print("---------------------")
    for e in hourly:
        print(
            f"{format_local_time(e, timezone_offset_s=tz_offset):>12}  "
            f"{format_temp(e.temperature, units=units):>5}  {e.status}"
        )

    print()
    print("Daily")
    print("-----")
    for d in daily:
        tmin = format_temp(d.temp_min, units=units)
        tmax = format_temp(d.temp_max, units=units)
        print(f"{d.date_local}  {tmin:>5} / {tmax:<5}  {d.status}")

