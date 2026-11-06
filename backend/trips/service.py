"""Plan a trip: routes -> checkpoints -> weather at each ETA -> risk -> summaries -> recommendation.

The corridor heatmap (hourly risk and weather for 49 one-hour slots, slider hours 0..48)
is a second call, so routes appear without waiting for hundreds of grid cells. It reuses
the cached routes and is fetched once per trip; the slider never needs another request.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.core.cache import cache

from .corridor import corridor_cells
from .display import display_line, risk_segments
from .geo import METERS_PER_MILE
from .providers.base import Place, RouteOption, RoutingProvider, routing_provider
from .providers.http import ProviderError
from .providers.open_meteo import GRIDS_DEG, HourlySeries, fetch_hourly, pick_grid
from .recommend import RouteSummary, recommend, summarize
from .risk import Assessment, Risk, assess, level_only
from .sampling import Checkpoint, place_checkpoints
from .slots import HOUR, first_slot_stamp, slot_for

HEATMAP_SLOTS = 49  # slider hours 0..48
ROUTE_IDS = "ABC"
ROUTE_CACHE_SECONDS = 10 * 60


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime  # timezone-aware
    load_lb: int
    spacing_mi: int


def plan_trip(req: TripRequest, provider: RoutingProvider | None = None) -> dict:
    provider = provider or routing_provider()
    options = _cached_routes(provider, req)

    spacing_m = req.spacing_mi * METERS_PER_MILE
    checkpoints = [place_checkpoints(o.profile, spacing_m) for o in options]
    slots = [[slot_for(req.departure, _eta(req, c)) for c in cps] for cps in checkpoints]

    # One weather fetch for every checkpoint of every route, up to the latest ETA.
    # Very long trips at fine spacing share forecast points so the free weather plan's
    # per-minute limit is never exceeded (see open_meteo.MAX_NEW_POINTS).
    hours = max(max(s) for s in slots) + 1
    slot0 = first_slot_stamp(req.departure)
    checkpoint_points = [(c.lat, c.lon) for cps in checkpoints for c in cps]
    grid = pick_grid(checkpoint_points, slot0, hours)
    checkpoint_series = fetch_hourly(checkpoint_points, slot0, hours, grid_deg=grid)

    routes, summaries, cursor = [], [], 0
    for route_id, option, cps, cp_slots in zip(ROUTE_IDS, options, checkpoints, slots, strict=False):
        weather = checkpoint_series[cursor : cursor + len(cps)]
        cursor += len(cps)
        assessments = [assess(w.at(s), req.load_lb) for w, s in zip(weather, cp_slots, strict=True)]
        summary = summarize(
            route_id,
            option.profile.distance_m,
            option.profile.duration_s,
            [(a.level, c.covers_m) for a, c in zip(assessments, cps, strict=True)],
        )
        summaries.append(summary)
        routes.append(_route_json(req, route_id, option, cps, cp_slots, weather, assessments, summary))

    recommendation = recommend(summaries)
    rank = {route_id: i + 1 for i, route_id in enumerate(recommendation.ranking)}
    for route in routes:
        route["rank"] = rank[route["id"]]
        route["recommended"] = route["id"] == recommendation.route_id

    return {
        "trip": {
            "origin": req.origin.__dict__,
            "destination": req.destination.__dict__,
            "departure": _iso(req.departure),
            "load_lb": req.load_lb,
            "spacing_mi": req.spacing_mi,
        },
        "provider": {"name": provider.name, "truck_routing": provider.is_truck_routing},
        "routes": routes,
        "recommendation": {
            "route_id": recommendation.route_id,
            "ranking": recommendation.ranking,
            "reason": recommendation.reason,
            "all_routes_have_no_travel": recommendation.all_routes_have_no_travel,
        },
        "notes": _notes(provider, len(options), recommendation.all_routes_have_no_travel, grid),
    }


def corridor_heatmap(req: TripRequest, provider: RoutingProvider | None = None) -> dict:
    """Hourly weather and risk on a grid around all routes, for slider hours 0..48."""
    provider = provider or routing_provider()
    options = _cached_routes(provider, req)  # normally a cache hit: the trip call just fetched them
    corridor = corridor_cells([o.profile.points for o in options])
    slot0 = first_slot_stamp(req.departure)
    series = fetch_hourly(corridor.cells, slot0, HEATMAP_SLOTS)
    hours = range(HEATMAP_SLOTS)
    return {
        "step_deg": corridor.step_deg,
        "slot0_start": _iso(slot0 - HOUR),  # slot k covers [slot0_start + k h, slot0_start + (k+1) h)
        "slots": HEATMAP_SLOTS,
        "cells": [[lon, lat] for lat, lon in corridor.cells],
        "risk": [[int(level_only(s.at(h), req.load_lb)) for h in hours] for s in series],
        "wind": [[round(s.wind_mph[h], 1) for h in hours] for s in series],
        "rain": [[round(s.rain_in_hr[h], 3) for h in hours] for s in series],
        "snow": [[round(s.snow_in_hr[h], 2) for h in hours] for s in series],
    }


def _cached_routes(provider: RoutingProvider, req: TripRequest) -> list[RouteOption]:
    """Routes for the same places and departure (to 15 min) are reused for 10 minutes."""
    dep = req.departure.astimezone(UTC)
    bucket = dep.replace(minute=dep.minute - dep.minute % 15, second=0, microsecond=0).isoformat()
    o, d = req.origin, req.destination
    raw = f"{provider.name}|{o.lat:.4f},{o.lon:.4f}|{d.lat:.4f},{d.lon:.4f}|{bucket}"
    key = "routes:v1:" + hashlib.sha1(raw.encode()).hexdigest()
    options = cache.get(key)
    if options is None:
        options = provider.routes(req.origin, req.destination, req.departure)
        if not options:
            raise ProviderError("No route was found between these places.", status=422)
        cache.set(key, options, ROUTE_CACHE_SECONDS)
    return options


def _eta(req: TripRequest, checkpoint: Checkpoint) -> datetime:
    return req.departure + timedelta(seconds=checkpoint.time_s)


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _route_json(
    req: TripRequest,
    route_id: str,
    option: RouteOption,
    checkpoints: list[Checkpoint],
    slots: list[int],
    weather: list[HourlySeries],
    assessments: list[Assessment],
    summary: RouteSummary,
) -> dict:
    line, times = display_line(option.profile)
    return {
        "id": route_id,
        "label": option.label,
        "distance_mi": round(summary.distance_m / METERS_PER_MILE, 1),
        "duration_s": round(summary.duration_s),
        "arrival": _iso(req.departure + timedelta(seconds=summary.duration_s)),
        "line": line,
        "line_times_s": times,
        "risk_segments": risk_segments(option.profile, checkpoints, [a.level for a in assessments]),
        "summary": {
            "miles_by_level": {level.name.lower(): round(summary.miles(level), 1) for level in Risk},
            "average_risk": round(summary.average_risk, 2),
            "worst": int(summary.worst),
        },
        "checkpoints": [
            _checkpoint_json(req, c, slot, series.at(slot), a)
            for c, slot, series, a in zip(checkpoints, slots, weather, assessments, strict=True)
        ],
    }


def _checkpoint_json(req: TripRequest, c: Checkpoint, slot: int, w, a: Assessment) -> dict:
    return {
        "mile": round(c.distance_m / METERS_PER_MILE, 1),
        "lat": round(c.lat, 5),
        "lon": round(c.lon, 5),
        "eta": _iso(_eta(req, c)),
        "slot": slot,
        "covers_mi": round(c.covers_m / METERS_PER_MILE, 1),
        "weather": {
            "wind_mph": round(w.wind_mph, 1),
            "gust_mph": round(w.gust_mph, 1),
            "rain_in_hr": round(w.rain_in_hr, 3),
            "snow_in_hr": round(w.snow_in_hr, 2),
        },
        "risk": {
            "level": int(a.level),
            "wind": int(a.wind),
            "rain": int(a.rain),
            "snow": int(a.snow),
            "load_rule": a.load_rule_applied,
            "reason": a.reason,
        },
    }


def _notes(provider: RoutingProvider, route_count: int, all_no_travel: bool, grid_deg: float) -> list[str]:
    notes = []
    if not provider.is_truck_routing:
        notes.append(
            "Routes come from the free OSRM demo server (car profile) because no TomTom key is set; "
            "travel times are for a car, not a truck."
        )
    if route_count < 3:
        notes.append(f"The routing service found {route_count} route{'s' if route_count != 1 else ''}, not 3.")
    if grid_deg > GRIDS_DEG[0]:
        km = round(grid_deg * 111)
        notes.append(
            f"This trip has many checkpoints, so checkpoints within about {km} km share one forecast point "
            "(the free weather service limits requests per minute)."
        )
    if all_no_travel:
        notes.append("Every route has No Travel conditions at this departure time. Try another departure time.")
    return notes
