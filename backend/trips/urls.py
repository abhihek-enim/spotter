from django.urls import path

from .views import GeocodeView, HealthView, HeatmapView, TripView

urlpatterns = [
    path("health", HealthView.as_view()),
    path("geocode", GeocodeView.as_view()),
    path("trips", TripView.as_view()),
    path("trips/heatmap", HeatmapView.as_view()),
]
