from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt
from . import views

app_name = "api"

urlpatterns = [
    path("docs", csrf_exempt(views.api_docs), name="docs"),
    path("controllers", csrf_exempt(views.api_controllers), name="controllers"),
    path("online", csrf_exempt(views.api_online), name="online"),
    path("events", csrf_exempt(views.api_events), name="events"),
    path("airports", csrf_exempt(views.api_airports), name="airports"),
    path("airports/<str:icao>", csrf_exempt(views.api_airport_detail), name="airport_detail"),
    path("metar/<str:icao>", csrf_exempt(views.api_metar), name="metar"),
    re_path(r"^custom/(?P<path>.+)$", csrf_exempt(views.serve_custom_endpoint), name="custom"),
]
