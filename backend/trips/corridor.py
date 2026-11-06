"""The heatmap grid: square cells covering a band around every route.

Cells sit on a fixed lat/lon lattice (multiples of the step), so the same place always
gets the same cell. That keeps the weather cache useful across trips.
The step grows for long trips so one trip never asks for more than `max_cells` points.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .geo import EARTH_RADIUS_M, LatLon, cumulative_distances, point_along

DEFAULT_STEPS_DEG = (0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0)
METERS_PER_DEG_LAT = EARTH_RADIUS_M * math.pi / 180


@dataclass(frozen=True)
class Corridor:
    step_deg: float
    cells: list[LatLon]  # cell centers


def corridor_cells(
    routes: Sequence[Sequence[LatLon]],
    buffer_m: float = 35_000,
    max_cells: int = 200,  # each cell is one weather call; Open-Meteo's free plan allows 600 a minute
    steps_deg: Sequence[float] = DEFAULT_STEPS_DEG,
) -> Corridor:
    """Cells whose center is within buffer_m of any route, at the finest step that fits."""
    samples = [p for route in routes for p in _samples(route, every_m=5_000)]
    for step in steps_deg:
        cells = _cells_near(samples, step, buffer_m, max_cells)
        if cells is not None:
            return Corridor(step_deg=step, cells=cells)
    # Even the coarsest step is too fine (a very long trip): keep the coarsest anyway.
    step = steps_deg[-1]
    return Corridor(step_deg=step, cells=_cells_near(samples, step, buffer_m, None) or [])


def _samples(route: Sequence[LatLon], every_m: float) -> list[LatLon]:
    """Points every `every_m` along a route, so long straight segments are covered too."""
    if len(route) < 2:
        return list(route)
    cum = cumulative_distances(route)
    count = max(1, math.ceil(cum[-1] / every_m))
    return [point_along(route, cum, cum[-1] * k / count) for k in range(count + 1)]


def _cells_near(samples: Sequence[LatLon], step: float, buffer_m: float, limit: int | None) -> list[LatLon] | None:
    """Lattice cells within buffer_m of any sample, or None as soon as there are > limit."""
    found: set[tuple[int, int]] = set()
    dlat = buffer_m / METERS_PER_DEG_LAT
    for lat, lon in samples:
        meters_per_deg_lon = METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians(lat)))
        dlon = buffer_m / meters_per_deg_lon
        for i in range(math.floor((lat - dlat) / step), math.ceil((lat + dlat) / step) + 1):
            for j in range(math.floor((lon - dlon) / step), math.ceil((lon + dlon) / step) + 1):
                if (i, j) in found:
                    continue
                dy = (i * step - lat) * METERS_PER_DEG_LAT
                dx = (j * step - lon) * meters_per_deg_lon
                if dx * dx + dy * dy <= buffer_m * buffer_m:
                    found.add((i, j))
                    if limit is not None and len(found) > limit:
                        return None
    return [(round(i * step, 4), round(j * step, 4)) for i, j in sorted(found)]
