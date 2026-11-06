"""Checkpoints along a route: where they are, when the truck gets there, how many miles each covers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .geo import LatLon, cumulative_distances, interpolate, lerp, point_along


@dataclass(frozen=True)
class RouteProfile:
    """A route as the routing API returned it, with distance and driving time at every point.

    cum_m[i] and cum_s[i] are the meters and seconds from the origin to points[i].
    """

    points: list[LatLon]
    cum_m: list[float]
    cum_s: list[float]

    @property
    def distance_m(self) -> float:
        return self.cum_m[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_s[-1]

    def time_at_distance(self, distance_m: float) -> float:
        return interpolate(self.cum_m, self.cum_s, distance_m)

    def distance_at_time(self, seconds: float) -> float:
        return interpolate(self.cum_s, self.cum_m, seconds)


def profile_from_anchors(points: Sequence[LatLon], anchors: Sequence[tuple[int, float, float]]) -> RouteProfile:
    """Build a full profile when the API gives distance/time only at some points.

    anchors are (point_index, meters, seconds), sorted by index, and must include the
    first and last point. Between two anchors, meters and seconds are spread over the
    points in proportion to the straight-line distance between them.
    """
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    if anchors[0][0] != 0 or anchors[-1][0] != len(points) - 1:
        raise ValueError("anchors must cover the first and last point")
    geo = cumulative_distances(points)
    cum_m = [0.0] * len(points)
    cum_s = [0.0] * len(points)
    for (i0, m0, s0), (i1, m1, s1) in zip(anchors, anchors[1:], strict=False):
        span = geo[i1] - geo[i0]
        for k in range(i0, i1 + 1):
            f = (geo[k] - geo[i0]) / span if span > 0 else (k - i0) / max(1, i1 - i0)
            cum_m[k] = lerp(m0, m1, f)
            cum_s[k] = lerp(s0, s1, f)
    return RouteProfile(points=list(points), cum_m=cum_m, cum_s=cum_s)


def profile_from_segments(points: Sequence[LatLon], seg_m: Sequence[float], seg_s: Sequence[float]) -> RouteProfile:
    """Build a profile when the API gives meters and seconds for every segment."""
    if len(seg_m) != len(points) - 1 or len(seg_s) != len(points) - 1:
        raise ValueError("need one distance and one duration per segment")
    cum_m, cum_s = [0.0], [0.0]
    for m, s in zip(seg_m, seg_s, strict=True):
        cum_m.append(cum_m[-1] + m)
        cum_s.append(cum_s[-1] + s)
    return RouteProfile(points=list(points), cum_m=cum_m, cum_s=cum_s)


@dataclass(frozen=True)
class Checkpoint:
    index: int
    distance_m: float  # from the origin
    lat: float
    lon: float
    time_s: float  # driving time from departure
    covers_m: float  # road length this checkpoint stands for


def checkpoint_distances(total_m: float, spacing_m: float) -> list[float]:
    """Origin, then every spacing_m, then the destination.

    A regular checkpoint closer than 1% of the spacing to the destination is dropped,
    so the destination is not sampled twice.
    """
    if spacing_m <= 0:
        raise ValueError("spacing must be positive")
    out = [0.0]
    d = spacing_m
    while d < total_m - spacing_m * 0.01:
        out.append(d)
        d += spacing_m
    if total_m > 0:
        out.append(total_m)
    return out


def coverage(distances: Sequence[float]) -> list[float]:
    """Miles each checkpoint stands for (decision 4 in the README).

    Every point of the road takes the risk of its NEAREST checkpoint, so a checkpoint
    covers half the gap to the one before plus half the gap to the one after.
    The origin and destination cover half a gap; the total equals the route length.
    """
    n = len(distances)
    if n == 1:
        return [0.0]
    out = []
    for i in range(n):
        before = distances[i] - distances[i - 1] if i > 0 else 0.0
        after = distances[i + 1] - distances[i] if i < n - 1 else 0.0
        out.append((before + after) / 2)
    return out


def place_checkpoints(profile: RouteProfile, spacing_m: float) -> list[Checkpoint]:
    distances = checkpoint_distances(profile.distance_m, spacing_m)
    covers = coverage(distances)
    out = []
    for i, (d, c) in enumerate(zip(distances, covers, strict=True)):
        lat, lon = point_along(profile.points, profile.cum_m, d)
        out.append(
            Checkpoint(
                index=i,
                distance_m=d,
                lat=lat,
                lon=lon,
                time_s=profile.time_at_distance(d),
                covers_m=c,
            )
        )
    return out
