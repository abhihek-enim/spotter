"""Route summaries and the recommendation.

The brief's order of preference:
  1. fewest Severe miles  2. fewest High miles  3. lowest average risk  4. shortest time

Decision 3 in the README puts No Travel in front of that: any route with No Travel miles
ranks below every route without them, and among those, fewer No Travel miles is better.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .geo import METERS_PER_MILE
from .risk import Risk


@dataclass(frozen=True)
class RouteSummary:
    route_id: str
    distance_m: float
    duration_s: float
    miles_by_level: dict[Risk, float] = field(default_factory=dict)
    average_risk: float = 0.0  # mile-weighted, 0 (all Low) .. 4 (all No Travel)
    worst: Risk = Risk.LOW

    def miles(self, level: Risk) -> float:
        return self.miles_by_level.get(level, 0.0)


def summarize(
    route_id: str,
    distance_m: float,
    duration_s: float,
    levels_and_coverage: Sequence[tuple[Risk, float]],
) -> RouteSummary:
    """Add up the miles at each risk level. levels_and_coverage = (level, meters covered)."""
    miles = {level: 0.0 for level in Risk}
    for level, covers_m in levels_and_coverage:
        miles[level] += covers_m / METERS_PER_MILE
    total = sum(miles.values())
    average = sum(level * m for level, m in miles.items()) / total if total > 0 else 0.0
    worst = max((level for level, _ in levels_and_coverage), default=Risk.LOW)
    return RouteSummary(
        route_id=route_id,
        distance_m=distance_m,
        duration_s=duration_s,
        miles_by_level=miles,
        average_risk=average,
        worst=worst,
    )


def ranking_key(s: RouteSummary) -> tuple:
    """Sort key: smaller is better.

    Miles are compared to 0.1 mile and average risk to 0.01, so rounding noise in the
    geometry cannot decide between routes; real ties fall through to travel time.
    """
    return (
        s.miles(Risk.NO_TRAVEL) > 0,
        round(s.miles(Risk.NO_TRAVEL), 1),
        round(s.miles(Risk.SEVERE), 1),
        round(s.miles(Risk.HIGH), 1),
        round(s.average_risk, 2),
        s.duration_s,
    )


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    ranking: list[str]  # best first
    reason: str
    all_routes_have_no_travel: bool


def recommend(summaries: Sequence[RouteSummary]) -> Recommendation:
    if not summaries:
        raise ValueError("no routes to compare")
    ranked = sorted(summaries, key=ranking_key)
    best = ranked[0]
    return Recommendation(
        route_id=best.route_id,
        ranking=[s.route_id for s in ranked],
        reason=explain(best, ranked[1] if len(ranked) > 1 else None),
        all_routes_have_no_travel=all(s.miles(Risk.NO_TRAVEL) > 0 for s in summaries),
    )


def explain(best: RouteSummary, runner_up: RouteSummary | None) -> str:
    """Name the first rule that separates the best route from the next one."""
    if runner_up is None:
        return "Only one route was found."
    a, b = ranking_key(best), ranking_key(runner_up)
    if a[0] != b[0]:
        return f"Only route {best.route_id} avoids No Travel conditions."
    if a[1] != b[1]:
        return f"Fewest No Travel miles ({a[1]:g} vs {b[1]:g})."
    if a[2] != b[2]:
        return f"Fewest Severe miles ({a[2]:g} vs {b[2]:g})."
    if a[3] != b[3]:
        return f"Fewest High miles ({a[3]:g} vs {b[3]:g})."
    if a[4] != b[4]:
        return f"Lowest average risk ({a[4]:.2f} vs {b[4]:.2f})."
    if a[5] != b[5]:
        return f"Same weather risk; fastest ({_hm(a[5])} vs {_hm(b[5])})."
    return "Routes tie on risk and time; the first one is shown."


def _hm(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min"
