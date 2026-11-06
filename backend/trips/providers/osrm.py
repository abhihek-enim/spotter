"""OSRM public demo server: a no-key stand-in used when TOMTOM_API_KEY is not set.

Limits, stated in the UI and README: car profile (not truck), and it often finds only
2 routes. Its usage policy allows light use only, so results are cached.
"""

from __future__ import annotations

from datetime import datetime

from ..sampling import profile_from_segments
from . import open_meteo
from .base import Place, RouteOption
from .http import ProviderError, get_json, make_session

ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{o_lon},{o_lat};{d_lon},{d_lat}"

_session = make_session()


class OsrmProvider:
    name = "OSRM demo (car profile)"
    is_truck_routing = False

    def routes(self, origin: Place, destination: Place, departure: datetime) -> list[RouteOption]:
        url = ROUTE_URL.format(o_lon=origin.lon, o_lat=origin.lat, d_lon=destination.lon, d_lat=destination.lat)
        params = {
            "alternatives": 3,
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "false",
        }
        status, body = get_json(_session, "OSRM routing", url, params)
        if status != 200 or not isinstance(body, dict) or body.get("code") != "Ok":
            message = body.get("message") if isinstance(body, dict) else None
            raise ProviderError(f"No route found: {message or f'HTTP {status}'}", status=422)
        return [parse_route(r) for r in body["routes"][:3]]

    def search(self, query: str) -> list[Place]:
        return open_meteo.search_places(query)


def parse_route(route: dict) -> RouteOption:
    """GeoJSON [lon, lat] coordinates + per-segment meters/seconds -> RouteProfile.

    OSRM's per-segment durations add up to slightly less than the route's total
    (turn penalties are not in the segments), so they are scaled to match the total.
    """
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    annotation = route["legs"][0]["annotation"]
    seg_m, seg_s = annotation["distance"], annotation["duration"]
    scale = route["duration"] / sum(seg_s) if sum(seg_s) > 0 else 1.0
    profile = profile_from_segments(points, seg_m, [s * scale for s in seg_s])
    return RouteOption(label=route["legs"][0].get("summary", ""), profile=profile)
