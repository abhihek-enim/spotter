"""TomTom Routing API (truck mode) and Search API.

- travelMode=truck with vehicleCommercial=true, so roads closed to trucks are avoided.
- departAt = the trip's departure, so travel times include typical traffic for that time.
- maxAlternatives=2: the best route plus up to 2 alternatives = 3 options.
- extendedRouteRepresentation=distance,travelTime adds a `progress` list giving meters and
  seconds from the start at route points; that is what gives each checkpoint its ETA.

The key is sent as a query parameter, so URLs are never logged (see http.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from ..sampling import profile_from_anchors
from .base import Place, RouteOption
from .http import ProviderError, get_json, make_session

ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{o_lat},{o_lon}:{d_lat},{d_lon}/json"
SEARCH_URL = "https://api.tomtom.com/search/2/search/{query}.json"

# Without a top speed, TomTom's truck mode came out as fast as its car mode
# (Dallas -> Chicago: 13.5 h truck vs 13.6 h car, ~72 mph average). Most fleets fit speed
# limiters, and ATRI's fleet surveys found 65 mph the most common setting, so ETAs assume
# a truck governed at 65 mph. TomTom still applies lower speed limits and traffic below
# the cap; the cap only matters on fast highways. (Dallas -> Chicago becomes 15.2 h.)
TRUCK_MAX_SPEED_MPH = 65
ROUTE_TIMEOUT_S = (5, 30)  # connect, read
TRUCK_MAX_SPEED_KMH = round(TRUCK_MAX_SPEED_MPH * 1.609344)  # TomTom takes km/h: 105

_session = make_session()


class TomTomProvider:
    name = "TomTom (truck)"
    is_truck_routing = True

    def __init__(self, key: str):
        self._key = key

    def routes(self, origin: Place, destination: Place, departure: datetime) -> list[RouteOption]:
        url = ROUTE_URL.format(o_lat=origin.lat, o_lon=origin.lon, d_lat=destination.lat, d_lon=destination.lon)
        params = {
            "key": self._key,
            "travelMode": "truck",
            "vehicleCommercial": "true",
            "vehicleMaxSpeed": TRUCK_MAX_SPEED_KMH,
            "maxAlternatives": 2,
            "traffic": "true",
            "departAt": depart_at_param(departure),
            "routeRepresentation": "polyline",
            "extendedRouteRepresentation": ["distance", "travelTime"],
        }
        # A 1,000-mile truck route with alternatives can take TomTom 15+ s (measured up to 17 s).
        status, body = get_json(_session, "TomTom routing", url, params, timeout=ROUTE_TIMEOUT_S)
        if status != 200 or not isinstance(body, dict) or "routes" not in body:
            raise ProviderError(f"No truck route found: {error_message(body, status)}", status=422)
        return [parse_route(r) for r in body["routes"][:3]]

    def search(self, query: str) -> list[Place]:
        params = {"key": self._key, "typeahead": "true", "limit": 6, "countrySet": "US,CA"}
        status, body = get_json(_session, "TomTom search", SEARCH_URL.format(query=quote(query, safe="")), params)
        if status != 200 or not isinstance(body, dict):
            raise ProviderError("Place search is unavailable right now.")
        return [
            Place(r["address"]["freeformAddress"], r["position"]["lat"], r["position"]["lon"])
            for r in body.get("results", [])
            if "position" in r and "address" in r
        ]


def depart_at_param(departure: datetime) -> str:
    """TomTom wants a future departure; anything within a minute of now is sent as 'now'."""
    if departure <= datetime.now(UTC) + timedelta(minutes=1):
        return "now"
    return departure.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def error_message(body: object, status: int) -> str:
    if isinstance(body, dict):
        detailed = body.get("detailedError") or {}
        if detailed.get("message"):
            return detailed["message"]
        error = body.get("error") or {}
        if isinstance(error, dict) and error.get("description"):
            return error["description"]
    return f"HTTP {status}"


def parse_route(route: dict) -> RouteOption:
    """Join the legs' points and turn the sparse `progress` entries into a full profile."""
    points: list[tuple[float, float]] = []
    for leg in route["legs"]:
        leg_points = [(p["latitude"], p["longitude"]) for p in leg["points"]]
        if points and leg_points and leg_points[0] == points[-1]:
            leg_points = leg_points[1:]  # legs share their joining point
        points.extend(leg_points)

    summary = route["summary"]
    last = len(points) - 1
    anchors = {0: (0.0, 0.0), last: (float(summary["lengthInMeters"]), float(summary["travelTimeInSeconds"]))}
    for entry in route.get("progress", []):
        index = entry.get("pointIndex")
        if index is not None and 0 < index < last and "distanceInMeters" in entry and "travelTimeInSeconds" in entry:
            anchors[index] = (float(entry["distanceInMeters"]), float(entry["travelTimeInSeconds"]))
    profile = profile_from_anchors(points, [(i, m, s) for i, (m, s) in sorted(anchors.items())])
    return RouteOption(label="", profile=profile)
