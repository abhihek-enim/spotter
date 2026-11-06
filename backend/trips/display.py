"""Geometry for the map. Calculations use the full route; the map gets lighter lines."""

from __future__ import annotations

from collections.abc import Sequence

from .geo import LatLon, simplify, sub_line
from .risk import Risk
from .sampling import Checkpoint, RouteProfile

TOLERANCE_M = 25  # points closer than this to the simplified line are dropped


def to_lon_lat(points: Sequence[LatLon]) -> list[list[float]]:
    """GeoJSON order is [lon, lat]; 5 decimals is about 1 m."""
    return [[round(lon, 5), round(lat, 5)] for lat, lon in points]


def display_line(profile: RouteProfile) -> tuple[list[list[float]], list[int]]:
    """Simplified route line plus the driving seconds at each kept point (for the truck marker)."""
    keep = simplify(profile.points, TOLERANCE_M)
    return to_lon_lat([profile.points[i] for i in keep]), [round(profile.cum_s[i]) for i in keep]


def risk_segments(profile: RouteProfile, checkpoints: Sequence[Checkpoint], levels: Sequence[Risk]) -> list[dict]:
    """The route cut into stretches coloured by risk, one stretch per run of equal levels.

    Each checkpoint owns the road nearest to it (decision 4): from halfway to the
    previous checkpoint to halfway to the next.
    """
    d = [c.distance_m for c in checkpoints]
    bounds = [0.0] + [(a + b) / 2 for a, b in zip(d, d[1:], strict=False)] + [profile.distance_m]
    segments: list[dict] = []
    start = 0.0
    for i, level in enumerate(levels):
        last = i == len(levels) - 1
        if last or levels[i + 1] != level:
            end = bounds[i + 1]
            if end > start:
                line = sub_line(profile.points, profile.cum_m, start, end)
                keep = simplify(line, TOLERANCE_M)
                segments.append({"level": int(level), "coordinates": to_lon_lat([line[k] for k in keep])})
            start = end
    return segments
