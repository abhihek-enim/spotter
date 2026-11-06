"""Input checks for the API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rest_framework import serializers

from .geo import haversine_m
from .providers.base import Place
from .service import TripRequest

MAX_DAYS_AHEAD = 7  # Open-Meteo forecasts 16 days; long trips plus the 48 h slider need room
MAX_LOAD_LB = 80_000


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class TripSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField(help_text="ISO 8601 with a time zone, e.g. 2026-11-04T08:00:00-06:00")
    load_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)
    spacing_mi = serializers.ChoiceField(choices=[10, 25, 50])

    def validate_departure(self, value: datetime) -> datetime:
        now = datetime.now(UTC)
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError("Departure is in the past.")
        if value > now + timedelta(days=MAX_DAYS_AHEAD):
            raise serializers.ValidationError(f"Departure must be within {MAX_DAYS_AHEAD} days (forecast range).")
        return value

    def validate(self, data: dict) -> dict:
        o, d = data["origin"], data["destination"]
        if haversine_m((o["lat"], o["lon"]), (d["lat"], d["lon"])) < 1_000:
            raise serializers.ValidationError("Origin and destination are the same place.")
        return data

    def to_trip_request(self) -> TripRequest:
        v = self.validated_data
        return TripRequest(
            origin=Place(**v["origin"]),
            destination=Place(**v["destination"]),
            departure=v["departure"],
            load_lb=v["load_lb"],
            spacing_mi=int(v["spacing_mi"]),
        )
