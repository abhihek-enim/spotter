"""HTTP endpoints. Kept thin: validate input, call the service, map errors to status codes."""

from __future__ import annotations

import hashlib
import logging

from django.core.cache import cache
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .providers.base import routing_provider
from .providers.http import ProviderError
from .serializers import TripSerializer
from .service import corridor_heatmap, plan_trip

log = logging.getLogger(__name__)
GEOCODE_CACHE_SECONDS = 24 * 60 * 60


class HealthView(APIView):
    """Cheap endpoint the page calls on load, which also wakes a sleeping free-tier server."""

    throttle_classes = []

    def get(self, request: Request) -> Response:
        provider = routing_provider()
        return Response({"ok": True, "routing": provider.name, "truck_routing": provider.is_truck_routing})


class GeocodeView(APIView):
    throttle_scope = "geocode"

    def get(self, request: Request) -> Response:
        query = " ".join(request.query_params.get("q", "").split())[:100]
        if len(query) < 2:
            return Response({"results": []})
        provider = routing_provider()
        key = "geocode:v1:" + hashlib.sha1(f"{provider.name}|{query.lower()}".encode()).hexdigest()
        places = cache.get(key)
        if places is None:
            try:
                places = provider.search(query)
            except ProviderError as exc:
                return Response({"detail": str(exc)}, status=exc.status)
            cache.set(key, places, GEOCODE_CACHE_SECONDS)
        return Response({"results": [p.__dict__ for p in places]})


class TripView(APIView):
    """Routes, checkpoints with ETA, weather and risk, summaries and the recommendation."""

    throttle_scope = "trips"
    work = staticmethod(plan_trip)

    def post(self, request: Request) -> Response:
        serializer = TripSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = self.work(serializer.to_trip_request())
        except ProviderError as exc:
            log.info("%s failed: %s", type(self).__name__, exc)
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(result)


class HeatmapView(TripView):
    """Same input as /trips; returns the 0-48 h weather grid around the trip's routes."""

    work = staticmethod(corridor_heatmap)
