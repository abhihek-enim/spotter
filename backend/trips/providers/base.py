"""Types shared by the providers, and the choice of routing provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from django.conf import settings

from ..sampling import RouteProfile


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RouteOption:
    label: str  # e.g. main roads; may be empty
    profile: RouteProfile


class RoutingProvider(Protocol):
    name: str
    is_truck_routing: bool

    def routes(self, origin: Place, destination: Place, departure: datetime) -> list[RouteOption]: ...

    def search(self, query: str) -> list[Place]: ...


def routing_provider() -> RoutingProvider:
    """TomTom (truck routing) when TOMTOM_API_KEY is set, otherwise the free OSRM demo server."""
    from .osrm import OsrmProvider
    from .tomtom import TomTomProvider

    if settings.TOMTOM_API_KEY:
        return TomTomProvider(settings.TOMTOM_API_KEY)
    return OsrmProvider()
