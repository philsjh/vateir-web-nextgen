from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("sessions/", views.my_sessions, name="my_sessions"),
    path("events/", views.events, name="events"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    path("events/<slug:slug>/remove-availability/", views.event_remove_availability, name="event_remove_availability"),
]
