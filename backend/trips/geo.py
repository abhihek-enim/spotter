"""Small geometry helpers. Points are (lat, lon) tuples in degrees; distances are meters."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance between two points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances(points: Sequence[LatLon]) -> list[float]:
    """Distance from the first point to each point along the line."""
    out = [0.0]
    for prev, cur in zip(points, points[1:], strict=False):
        out.append(out[-1] + haversine_m(prev, cur))
    return out


def locate(xs: Sequence[float], x: float) -> tuple[int, float]:
    """Find where x falls in the increasing list xs.

    Returns (i, f): x lies between xs[i] and xs[i + 1], a fraction f of the way.
    x outside the range is clamped to the first or last segment.
    """
    if len(xs) < 2:
        return 0, 0.0
    i = bisect_right(xs, x) - 1
    i = max(0, min(i, len(xs) - 2))
    span = xs[i + 1] - xs[i]
    f = 0.0 if span <= 0 else (x - xs[i]) / span
    return i, max(0.0, min(1.0, f))


def lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def interpolate(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    """Linear interpolation of ys at x (xs increasing)."""
    if len(ys) == 1:
        return ys[0]
    i, f = locate(xs, x)
    return lerp(ys[i], ys[i + 1], f)


def point_along(points: Sequence[LatLon], cum_m: Sequence[float], distance_m: float) -> LatLon:
    """The point at a given distance along a line (straight between vertices)."""
    if len(points) == 1:
        return points[0]
    i, f = locate(cum_m, distance_m)
    (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
    return lerp(lat1, lat2, f), lerp(lon1, lon2, f)


def sub_line(points: Sequence[LatLon], cum_m: Sequence[float], start_m: float, end_m: float) -> list[LatLon]:
    """The part of a line between two distances along it, with exact cut points at both ends."""
    inner = [p for p, d in zip(points, cum_m, strict=True) if start_m < d < end_m]
    return [point_along(points, cum_m, start_m), *inner, point_along(points, cum_m, end_m)]


def simplify(points: Sequence[LatLon], tolerance_m: float) -> list[int]:
    """Douglas-Peucker line simplification. Returns the indices of the points to keep.

    Used only to make the map geometry lighter; all calculations use the full line.
    """
    n = len(points)
    if n <= 2:
        return list(range(n))
    # Project to a flat x/y plane in meters (fine at the scale of one segment test).
    lat0 = math.radians(points[0][0])
    kx = EARTH_RADIUS_M * math.cos(lat0) * math.pi / 180
    ky = EARTH_RADIUS_M * math.pi / 180
    xy = [(lon * kx, lat * ky) for lat, lon in points]

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        far_index, far_dist = -1, tolerance_m
        for k in range(start + 1, end):
            d = _segment_distance(xy[k], xy[start], xy[end])
            if d > far_dist:
                far_index, far_dist = k, d
        if far_index != -1:
            keep[far_index] = True
            stack.append((start, far_index))
            stack.append((far_index, end))
    return [i for i, kept in enumerate(keep) if kept]


def _segment_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
