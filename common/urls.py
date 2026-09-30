from django.urls import path
from .views import telemetry_events_view

urlpatterns = [
    path('api/telemetry/events/', telemetry_events_view, name='telemetry_events'),
]
