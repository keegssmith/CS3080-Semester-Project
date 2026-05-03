# Simple data models shared across CLI + GUI.

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Location:
    name: str
    country: str | None
    state: str | None
    lat: float
    lon: float

    @property
    def display_name(self) -> str:
        parts: list[str] = [self.name]
        if self.state:
            parts.append(self.state)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


@dataclass(frozen=True)
class CurrentConditions:
    location_name: str
    temperature: float
    feels_like: float | None
    humidity: int | None
    wind_speed: float | None
    status: str
    icon: str | None


@dataclass(frozen=True)
class ForecastEntry:
    utc_dt: datetime
    temperature: float
    status: str
    icon: str | None

    @staticmethod
    def from_unix(
        utc_seconds: int, temperature: float, status: str, icon: str | None
    ) -> ForecastEntry:
        return ForecastEntry(
            datetime.fromtimestamp(utc_seconds, tz=timezone.utc),
            temperature,
            status,
            icon,
        )


@dataclass(frozen=True)
class DailySummary:
    date_local: str  # YYYY-MM-DD in locations local time
    temp_min: float
    temp_max: float
    status: str
    icon: str | None
