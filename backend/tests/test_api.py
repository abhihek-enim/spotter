"""The whole trip through the API, with the outside services faked."""

from datetime import UTC, datetime, timedelta

import pytest
import responses
from rest_framework.test import APIClient

from trips.providers.base import Place, RouteOption
from trips.providers.open_meteo import GEOCODING_URL
from trips.sampling import profile_from_segments
from trips.service import TripRequest, plan_trip

from .conftest import load_fixture

FORT_WORTH = {"label": "Fort Worth, Texas, US", "lat": 32.7555, "lon": -97.3308}
DALLAS = {"label": "Dallas, Texas, US", "lat": 32.7767, "lon": -96.797}


def trip_body(**overrides):
    body = {
        "origin": FORT_WORTH,
        "destination": DALLAS,
        "departure": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "load_lb": 20_000,
        "spacing_mi": 10,
    }
    return body | overrides


@pytest.fixture
def client():
    return APIClient()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["truck_routing"] is False  # no TomTom key in tests


@responses.activate
def test_geocode(client):
    responses.add(responses.GET, GEOCODING_URL, json=load_fixture("open_meteo_geocode_dallas.json"))
    results = client.get("/api/geocode", {"q": "Dallas"}).json()["results"]
    assert results[0] == {
        "label": "Dallas, Texas, US",
        "lat": pytest.approx(32.78, abs=0.01),
        "lon": pytest.approx(-96.81, abs=0.01),
    }


def test_geocode_ignores_one_letter(client):
    assert client.get("/api/geocode", {"q": "D"}).json() == {"results": []}


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"departure": "2020-01-01T00:00:00Z"}, "departure"),
        ({"spacing_mi": 15}, "spacing_mi"),
        ({"load_lb": -1}, "load_lb"),
        ({"load_lb": 90_000}, "load_lb"),
        ({"destination": FORT_WORTH}, "non_field_errors"),
    ],
)
def test_trip_validation(client, override, field):
    response = client.post("/api/trips", trip_body(**override), format="json")
    assert response.status_code == 400
    assert field in response.json()


def test_trip_end_to_end_with_recorded_osrm_routes(client, fake_weather):
    weather = fake_weather(lambda lat, lon, h: {})
    weather.add(
        responses.GET,
        "https://router.project-osrm.org/route/v1/driving/-97.3308,32.7555;-96.797,32.7767",
        json=load_fixture("osrm_fort_worth_dallas.json"),
    )
    response = client.post("/api/trips", trip_body(), format="json")
    assert response.status_code == 200, response.content
    body = response.json()

    assert [r["id"] for r in body["routes"]] == ["A", "B"]
    route = body["routes"][0]
    assert route["distance_mi"] == pytest.approx(32.4, abs=0.1)
    # 10-mile spacing on a 32-mile route: miles 0, 10, 20, 30 and the destination.
    assert [c["mile"] for c in route["checkpoints"]] == [0, 10, 20, 30, route["distance_mi"]]
    assert sum(c["covers_mi"] for c in route["checkpoints"]) == pytest.approx(route["distance_mi"], abs=0.2)
    assert route["summary"]["miles_by_level"]["low"] == pytest.approx(route["distance_mi"], abs=0.1)
    assert body["recommendation"]["reason"].startswith("Same weather risk; fastest")
    assert body["recommendation"]["route_id"] == "A"
    assert any("OSRM" in n for n in body["notes"]) and any("found 2 routes" in n for n in body["notes"])

    # The heatmap call reuses the cached routes: no second routing request.
    routing_calls = sum("router.project-osrm.org" in c.request.url for c in weather.calls)
    heatmap = client.post("/api/trips/heatmap", trip_body(), format="json").json()
    assert sum("router.project-osrm.org" in c.request.url for c in weather.calls) == routing_calls
    assert len(heatmap["risk"]) == len(heatmap["cells"]) > 0
    assert all(len(row) == 49 for row in heatmap["risk"] + heatmap["wind"] + heatmap["rain"] + heatmap["snow"])
    assert heatmap["slots"] == 49


def test_retry_logs_never_show_urls():
    import logging

    # urllib3 logs full URLs (with the TomTom key) when it retries; settings silence it.
    assert logging.getLogger("urllib3.connectionpool").getEffectiveLevel() >= logging.ERROR


def test_routing_failure_is_a_clean_error(client, fake_weather):
    mock = fake_weather(lambda lat, lon, h: {})
    mock.add(
        responses.GET,
        "https://router.project-osrm.org/route/v1/driving/-97.3308,32.7555;-96.797,32.7767",
        status=400,
        json={"code": "NoRoute", "message": "Impossible route"},
    )
    response = client.post("/api/trips", trip_body(), format="json")
    assert response.status_code == 422
    assert "Impossible route" in response.json()["detail"]


# ---------------------------------------------------------------- the decision logic on a made-up map
class TwoRoutes:
    """Route A runs straight east along 35N; route B detours north through 36N and is slower."""

    name = "test"
    is_truck_routing = True

    def routes(self, origin, destination, departure):
        def line(points, hours):
            seg = [10_000.0] * (len(points) - 1)
            return profile_from_segments(points, seg, [hours * 3600 / len(seg)] * len(seg))

        a = [(35.0, -100.0 + 0.1 * k) for k in range(11)]
        b = [(35.0, -100.0), (35.5, -100.0), (36.0, -99.5), (35.5, -99.0), (35.0, -99.0)]
        return [RouteOption("south", line(a, 2)), RouteOption("north", line(b, 3))]

    def search(self, query):
        return []


def request(load_lb):
    return TripRequest(Place("O", 35.0, -100.0), Place("D", 35.0, -99.0), datetime.now(UTC), load_lb, 10)


def test_storm_on_the_fast_route_sends_the_truck_north(fake_weather):
    fake_weather(lambda lat, lon, h: {"wind_speed_10m": 48.0} if lat < 35.3 and -99.8 < lon < -99.2 else {})
    result = plan_trip(request(load_lb=20_000), provider=TwoRoutes())
    a = next(r for r in result["routes"] if r["id"] == "A")
    assert a["summary"]["miles_by_level"]["severe"] > 0
    assert result["recommendation"]["route_id"] == "B"
    assert result["recommendation"]["reason"].startswith("Fewest Severe miles")
    worst = max(a["checkpoints"], key=lambda c: c["risk"]["level"])
    assert worst["risk"]["reason"] == "Wind 48 mph"


def test_same_storm_with_a_heavy_load_is_no_travel(fake_weather):
    fake_weather(lambda lat, lon, h: {"wind_speed_10m": 48.0} if lat < 35.3 and -99.8 < lon < -99.2 else {})
    result = plan_trip(request(load_lb=35_000), provider=TwoRoutes())
    a = next(r for r in result["routes"] if r["id"] == "A")
    assert a["summary"]["miles_by_level"]["no_travel"] > 0
    assert result["recommendation"]["reason"] == "Only route B avoids No Travel conditions."
    assert any(c["risk"]["load_rule"] for c in a["checkpoints"])


def test_weather_is_read_at_each_checkpoints_eta(fake_weather):
    # Snow starts 1 hour after departure everywhere. Route A takes 2 hours, so its
    # first checkpoints (reached in the first hour) are Low and the later ones are High.
    fake_weather(lambda lat, lon, h: {"snowfall": 1.5} if h >= 1 else {})
    departure = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(minutes=1)
    req = TripRequest(Place("O", 35.0, -100.0), Place("D", 35.0, -99.0), departure, 0, 10)
    a = plan_trip(req, provider=TwoRoutes())["routes"][0]
    levels = [(c["slot"], c["risk"]["level"]) for c in a["checkpoints"]]
    assert levels[0] == (0, 0)
    assert all(level == (2 if slot >= 1 else 0) for slot, level in levels)
    assert {slot for slot, _ in levels} == {0, 1, 2}


def test_long_trips_share_forecast_points_and_say_so(fake_weather, monkeypatch):
    from trips.providers import open_meteo

    monkeypatch.setattr(open_meteo, "MAX_NEW_POINTS", 5)  # pretend the trip is huge
    fake_weather(lambda lat, lon, h: {})
    result = plan_trip(request(load_lb=0), provider=TwoRoutes())
    assert any("share one forecast point" in n for n in result["notes"])
    assert result["routes"][0]["checkpoints"]  # the trip still works
