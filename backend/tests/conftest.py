"""Shared test helpers: an empty cache per test, and a fake Open-Meteo that answers any request."""

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.core.cache import cache

from trips.providers.open_meteo import FORECAST_URL

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def empty_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake_weather():
    """Install a fake Open-Meteo. Pass a function (lat, lon, hour) -> dict of hourly values.

    Usage: fake_weather(lambda lat, lon, h: {"wind_speed_10m": 50 if lat > 40 else 5})
    Missing variables default to calm weather. Returns the `responses` mock to count calls.
    """
    mock = responses.RequestsMock(assert_all_requests_are_fired=False)
    mock.start()

    def install(values_for):
        def callback(request):
            q = parse_qs(urlparse(request.url).query)
            lats = [float(v) for v in q["latitude"][0].split(",")]
            lons = [float(v) for v in q["longitude"][0].split(",")]
            start = datetime.fromisoformat(q["start_hour"][0])
            end = datetime.fromisoformat(q["end_hour"][0])
            hours = int((end - start).total_seconds() // 3600) + 1
            items = []
            for lat, lon in zip(lats, lons, strict=True):
                calm = {"wind_speed_10m": 5.0, "wind_gusts_10m": 10.0, "rain": 0.0, "showers": 0.0, "snowfall": 0.0}
                rows = [calm | values_for(lat, lon, h) for h in range(hours)]
                hourly = {name: [row[name] for row in rows] for name in calm}
                hourly["time"] = [f"t{h}" for h in range(hours)]
                items.append({"latitude": lat, "longitude": lon, "hourly": hourly})
            body = items if len(items) > 1 else items[0]
            return 200, {"Content-Type": "application/json"}, json.dumps(body)

        mock.add_callback(responses.GET, FORECAST_URL, callback=callback)
        return mock

    yield install
    mock.stop()
    mock.reset()
