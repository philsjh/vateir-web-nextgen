from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("sessions/", views.my_sessions, name="my_sessions"),
    path("events/", views.events, name="events"),
]
