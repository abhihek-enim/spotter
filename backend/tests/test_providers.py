from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from trips.geo import cumulative_distances
from trips.providers import osrm, tomtom
from trips.providers.base import Place
from trips.providers.http import ProviderError
from trips.providers.open_meteo import GEOCODING_URL, fetch_hourly, search_places

from .conftest import load_fixture

START = datetime(2026, 11, 4, 15, tzinfo=UTC)


# ---------------------------------------------------------------- OSRM (recorded response)
def test_osrm_recorded_response_parses_into_profiles():
    body = load_fixture("osrm_fort_worth_dallas.json")
    options = [osrm.parse_route(r) for r in body["routes"]]
    assert len(options) == 2
    for option, raw in zip(options, body["routes"], strict=True):
        profile = option.profile
        assert len(profile.points) == len(raw["geometry"]["coordinates"])
        assert profile.distance_m == pytest.approx(raw["distance"], rel=1e-3)
        assert profile.duration_s == pytest.approx(raw["duration"])  # scaled to the route total
        assert profile.points[0][0] == pytest.approx(32.75, abs=0.05)  # (lat, lon) order
        assert all(b >= a for a, b in zip(profile.cum_s, profile.cum_s[1:], strict=False))


# ---------------------------------------------------------------- TomTom (recorded response)
def test_tomtom_recorded_response_gives_three_truck_routes():
    """Real reply for Fort Worth -> Dallas (recorded 6 Nov 2026, key removed): sparse progress entries."""
    body = load_fixture("tomtom_fort_worth_dallas.json")
    options = [tomtom.parse_route(r) for r in body["routes"]]
    assert len(options) == 3
    for option, raw in zip(options, body["routes"], strict=True):
        profile, summary = option.profile, raw["summary"]
        assert len(raw["progress"]) < len(profile.points)  # TomTom gives time only at some points
        assert profile.distance_m == pytest.approx(summary["lengthInMeters"])
        assert profile.duration_s == pytest.approx(summary["travelTimeInSeconds"])
        assert all(b >= a for a, b in zip(profile.cum_s, profile.cum_s[1:], strict=False))
        assert profile.points[0][0] == pytest.approx(32.75, abs=0.05)


# ---------------------------------------------------------------- TomTom (shaped like the docs)
def tomtom_route(n_points=21, length_m=20_000, seconds=1_200, progress_every=5):
    """A route in TomTom's documented shape: legs[].points and a sparse progress list."""
    points = [{"latitude": 35.0, "longitude": -100.0 + 0.01 * k} for k in range(n_points)]
    progress = [
        {
            "pointIndex": k,
            "distanceInMeters": length_m * k / (n_points - 1),
            "travelTimeInSeconds": seconds * k / (n_points - 1),
        }
        for k in range(0, n_points, progress_every)
    ]
    return {
        "summary": {"lengthInMeters": length_m, "travelTimeInSeconds": seconds},
        "legs": [{"points": points}],
        "progress": progress,
    }


def test_tomtom_route_uses_progress_for_time():
    option = tomtom.parse_route(tomtom_route())
    assert option.profile.distance_m == 20_000
    assert option.profile.duration_s == 1_200
    assert option.profile.cum_s[10] == pytest.approx(600)
    assert option.profile.cum_s[12] == pytest.approx(720)


def test_tomtom_legs_are_joined_without_duplicating_the_shared_point():
    route = tomtom_route(n_points=11)
    first, second = route["legs"][0]["points"][:6], route["legs"][0]["points"][5:]
    route["legs"] = [{"points": first}, {"points": second}]
    assert len(tomtom.parse_route(route).profile.points) == 11


def test_tomtom_without_progress_falls_back_to_summary_totals():
    route = tomtom_route()
    del route["progress"]
    profile = tomtom.parse_route(route).profile
    geo = cumulative_distances(profile.points)
    assert profile.cum_s[10] == pytest.approx(1_200 * geo[10] / geo[-1])


def test_tomtom_error_message():
    assert (
        tomtom.error_message({"detailedError": {"message": "Unable to find a route"}}, 400) == "Unable to find a route"
    )
    assert tomtom.error_message({"error": {"description": "Bad key"}}, 403) == "Bad key"
    assert tomtom.error_message("oops", 500) == "HTTP 500"


def test_tomtom_depart_at():
    assert tomtom.depart_at_param(datetime.now(UTC)) == "now"
    later = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert tomtom.depart_at_param(later) == "2030-01-02T03:04:05Z"


@responses.activate
def test_tomtom_key_never_appears_in_errors():
    responses.add(
        responses.GET,
        url=responses.matchers.re.compile(r"https://api\.tomtom\.com/.*"),
        body=requests.ConnectionError("https://api.tomtom.com/...?key=SECRET123"),
    )
    provider = tomtom.TomTomProvider("SECRET123")
    with pytest.raises(ProviderError) as info:
        provider.routes(Place("A", 35, -100), Place("B", 36, -99), datetime.now(UTC) + timedelta(hours=1))
    assert "SECRET123" not in str(info.value)


@responses.activate
def test_tomtom_request_asks_for_truck_routes_with_alternatives():
    responses.add(
        responses.GET,
        url=responses.matchers.re.compile(r"https://api\.tomtom\.com/routing/.*"),
        json={"routes": [tomtom_route()]},
    )
    tomtom.TomTomProvider("k").routes(Place("A", 35, -100), Place("B", 35, -99.8), datetime.now(UTC))
    sent = responses.calls[0].request.url
    for part in (
        "travelMode=truck",
        "vehicleCommercial=true",
        "maxAlternatives=2",
        "vehicleMaxSpeed=105",  # 65 mph speed-limited truck
        "extendedRouteRepresentation=distance",
        "extendedRouteRepresentation=travelTime",
        "departAt=now",
    ):
        assert part in sent


# ---------------------------------------------------------------- Open-Meteo
def test_rain_is_rain_plus_showers(fake_weather):
    fake_weather(lambda lat, lon, h: {"rain": 0.1, "showers": 0.15, "snowfall": 0.4, "wind_speed_10m": 30.0})
    [series] = fetch_hourly([(35.0, -100.0)], START, hours=3)
    assert series.rain_in_hr == [0.25, 0.25, 0.25]
    assert series.at(0).snow_in_hr == 0.4
    assert series.at(2).wind_mph == 30.0


def test_points_are_rounded_deduplicated_cached_and_keep_their_order(fake_weather):
    mock = fake_weather(lambda lat, lon, h: {"wind_speed_10m": lat})  # wind = latitude, to tell points apart
    points = [(36.001, -99.0), (35.0, -100.0), (36.0, -99.002)]  # first and last round to the same point
    series = fetch_hourly(points, START, hours=49)
    assert [s.wind_mph[0] for s in series] == [36.0, 35.0, 36.0]
    assert len(series[0].wind_mph) == 49
    sent = parse_qs(urlparse(mock.calls[0].request.url).query)
    assert sent["latitude"] == ["36.0,35.0"]  # 3 points, 2 unique after rounding
    fetch_hourly(points, START, hours=49)
    assert len(mock.calls) == 1  # second time comes from the cache


def test_window_is_fetched_in_whole_days(fake_weather):
    mock = fake_weather(lambda lat, lon, h: {})
    fetch_hourly([(35.0, -100.0)], START, hours=30)
    url = mock.calls[0].request.url
    assert "start_hour=2026-11-04T15%3A00" in url
    assert "end_hour=2026-11-06T14%3A00" in url  # 48 rows


@responses.activate
def test_open_meteo_error_is_reported():
    responses.add(
        responses.GET,
        "https://api.open-meteo.com/v1/forecast",
        status=400,
        json={"error": True, "reason": "Latitude must be in range"},
    )
    with pytest.raises(ProviderError, match="Latitude must be in range"):
        fetch_hourly([(35.0, -100.0)], START, hours=1)


@responses.activate
def test_place_search_keeps_us_and_canada_only():
    body = load_fixture("open_meteo_geocode_dallas.json")
    body["results"].insert(
        0, {"name": "Dallas", "admin1": "Somewhere", "country_code": "AU", "latitude": 1, "longitude": 2}
    )
    responses.add(responses.GET, GEOCODING_URL, json=body)
    places = search_places("Dallas")
    assert places[0].label == "Dallas, Texas, US"
    assert all(not p.label.endswith("AU") for p in places)
    assert len(places) <= 6


def test_grid_stays_fine_for_normal_trips_and_coarsens_for_huge_ones():
    from trips.providers.open_meteo import pick_grid

    few = [(35.0, -100.0 + 0.2 * k) for k in range(100)]
    assert pick_grid(few, START, 24) == 0.01
    # 1,000 checkpoints 0.02 deg apart: 400 unique points at 0.05 deg, 200 at 0.1 deg.
    many = [(35.0, -100.0 + 0.02 * k) for k in range(1000)]
    assert pick_grid(many, START, 24, max_new_points=350) == 0.1


def test_cached_points_do_not_count_against_the_budget(fake_weather):
    from trips.providers.open_meteo import pick_grid

    fake_weather(lambda lat, lon, h: {})
    points = [(35.0, -100.0 + 0.2 * k) for k in range(40)]
    assert pick_grid(points, START, 24, max_new_points=10) > 0.01
    fetch_hourly(points, START, 24)  # now cached at the fine grid
    assert pick_grid(points, START, 24, max_new_points=10) == 0.01


@responses.activate
def test_open_meteo_per_minute_limit_gives_a_clear_message_without_retrying():
    responses.add(
        responses.GET,
        "https://api.open-meteo.com/v1/forecast",
        status=429,
        json={"error": True, "reason": "Minutely API request limit exceeded. Please try again in one minute."},
    )
    with pytest.raises(ProviderError, match="limited number of requests per minute") as info:
        fetch_hourly([(35.0, -100.0)], START, hours=1)
    assert info.value.status == 503
    assert len(responses.calls) == 1  # no pointless instant retries
