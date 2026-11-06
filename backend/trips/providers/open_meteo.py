"""Open-Meteo: hourly forecasts for many points (no API key), plus place search.

Units are requested as mph and inches, which are the brief's units.
- rain_in_hr = rain + showers. Open-Meteo reports large-scale rain and convective showers
  separately; rain alone would miss thunderstorms.
- snow_in_hr = snowfall: inches of snow (not water equivalent) over the hour.
Both are totals for the hour before each timestamp (see slots.py).
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.cache import cache

from ..geo import LatLon
from ..risk import Weather
from .base import Place
from .http import ProviderError, get_json, make_session

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
POINTS_PER_REQUEST = 50  # measured: 50 points answer in ~1.5 s
PARALLEL_REQUESTS = 3  # Open-Meteo dropped connections at 8 at once
CACHE_SECONDS = 60 * 60  # forecasts update about hourly

# Open-Meteo's free plan counts every point as one call and allows 600 calls a minute.
# A trip's checkpoints may use at most MAX_NEW_POINTS uncached points, which leaves room
# for its heatmap (at most 200 cells, see corridor.py) in the same minute.
MAX_NEW_POINTS = 350
# Points are snapped to a grid before fetching. 0.01 deg is about 1 km, finer than the
# weather models themselves (1.5-13 km). Only very long trips at 10-mile spacing need a
# coarser grid, where nearby checkpoints then share one forecast point.
GRIDS_DEG = (0.01, 0.05, 0.1, 0.2, 0.5)
RATE_LIMIT_MESSAGE = (
    "The free weather service allows a limited number of requests per minute. Please try again in a minute."
)

_session = make_session(retry_statuses=(500, 502, 503, 504))  # retrying a per-minute limit at once does not help


@dataclass(frozen=True)
class HourlySeries:
    """One point's forecast, one value per hour from the requested start hour."""

    wind_mph: list[float]
    gust_mph: list[float]
    rain_in_hr: list[float]
    snow_in_hr: list[float]

    def at(self, hour: int) -> Weather:
        return Weather(
            wind_mph=self.wind_mph[hour],
            gust_mph=self.gust_mph[hour],
            rain_in_hr=self.rain_in_hr[hour],
            snow_in_hr=self.snow_in_hr[hour],
        )

    def head(self, hours: int) -> HourlySeries:
        return HourlySeries(
            self.wind_mph[:hours], self.gust_mph[:hours], self.rain_in_hr[:hours], self.snow_in_hr[:hours]
        )


def _window(start_utc: datetime, hours: int) -> tuple[str, str, int]:
    """The request window, in whole days so that cache entries are reusable across trips."""
    fetch_hours = math.ceil(hours / 24) * 24
    start = start_utc.strftime("%Y-%m-%dT%H:00")
    end = (start_utc + timedelta(hours=fetch_hours - 1)).strftime("%Y-%m-%dT%H:00")
    return start, end, fetch_hours


def _snap(point: LatLon, grid_deg: float) -> LatLon:
    lat, lon = point
    return round(round(lat / grid_deg) * grid_deg, 4), round(round(lon / grid_deg) * grid_deg, 4)


def _cache_key(point: LatLon, start: str, fetch_hours: int) -> str:
    return f"om:v2:{point[0]}:{point[1]}:{start}:{fetch_hours}"


def pick_grid(points: list[LatLon], start_utc: datetime, hours: int, max_new_points: int | None = None) -> float:
    """The finest grid at which the points not already cached fit in the per-minute budget."""
    budget = MAX_NEW_POINTS if max_new_points is None else max_new_points
    start, _, fetch_hours = _window(start_utc, hours)
    for grid in GRIDS_DEG:
        keys = list({_cache_key(_snap(p, grid), start, fetch_hours) for p in points})
        if len(keys) - len(cache.get_many(keys)) <= budget:
            return grid
    return GRIDS_DEG[-1]


def fetch_hourly(
    points: list[LatLon], start_utc: datetime, hours: int, grid_deg: float = GRIDS_DEG[0]
) -> list[HourlySeries]:
    """Hourly weather for each point, for `hours` rows starting at the row stamped `start_utc`.

    Points are snapped to `grid_deg` and cached for an hour, so overlapping trips share data.
    """
    start, end, fetch_hours = _window(start_utc, hours)
    rounded = [_snap(p, grid_deg) for p in points]
    key_of = {p: _cache_key(p, start, fetch_hours) for p in dict.fromkeys(rounded)}
    found: dict[str, HourlySeries] = cache.get_many(list(key_of.values()))
    missing = [p for p, key in key_of.items() if key not in found]

    batches = [missing[i : i + POINTS_PER_REQUEST] for i in range(0, len(missing), POINTS_PER_REQUEST)]
    if batches:
        with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
            results = list(pool.map(lambda batch: _request(batch, start, end, fetch_hours), batches))
        fresh = {
            key_of[p]: s
            for batch, series in zip(batches, results, strict=True)
            for p, s in zip(batch, series, strict=True)
        }
        cache.set_many(fresh, CACHE_SECONDS)
        found.update(fresh)

    return [found[key_of[p]].head(hours) for p in rounded]


def _request(points: list[LatLon], start: str, end: str, expected_hours: int) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{lat}" for lat, _ in points),
        "longitude": ",".join(f"{lon}" for _, lon in points),
        "hourly": ",".join(VARIABLES),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "start_hour": start,
        "end_hour": end,
    }
    status, body = get_json(_session, "Open-Meteo", FORECAST_URL, params)
    if status == 429:
        raise ProviderError(RATE_LIMIT_MESSAGE, status=503)
    if status != 200:
        reason = body.get("reason", "") if isinstance(body, dict) else ""
        raise ProviderError(f"Weather forecast unavailable: {reason or f'HTTP {status}'}")
    items = body if isinstance(body, list) else [body]  # one point -> one object
    if len(items) != len(points):
        raise ProviderError("Weather forecast came back for the wrong number of places.")
    return [_parse(item, expected_hours) for item in items]


def _parse(item: dict, expected_hours: int) -> HourlySeries:
    hourly = item.get("hourly") or {}
    if len(hourly.get("time", [])) != expected_hours:
        raise ProviderError("Weather forecast does not cover the whole trip window.")

    def column(name: str) -> list[float]:
        return [v if v is not None else 0.0 for v in hourly.get(name, [None] * expected_hours)]

    rain, showers = column("rain"), column("showers")
    return HourlySeries(
        wind_mph=column("wind_speed_10m"),
        gust_mph=column("wind_gusts_10m"),
        rain_in_hr=[round(r + s, 3) for r, s in zip(rain, showers, strict=True)],
        snow_in_hr=column("snowfall"),
    )


def search_places(query: str, countries: tuple[str, ...] = ("US", "CA")) -> list[Place]:
    """Town and city search (Open-Meteo / GeoNames). Used when no TomTom key is set."""
    status, body = get_json(
        _session, "Place search", GEOCODING_URL, {"name": query, "count": 20, "language": "en", "format": "json"}
    )
    if status != 200 or not isinstance(body, dict):
        raise ProviderError("Place search is unavailable right now.")
    places = []
    for r in body.get("results", []):
        if r.get("country_code") not in countries:
            continue
        parts = [r.get("name"), r.get("admin1"), r.get("country_code")]
        places.append(Place(", ".join(p for p in parts if p), r["latitude"], r["longitude"]))
    return places[:6]
