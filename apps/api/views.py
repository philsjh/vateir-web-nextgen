"""
VATéir Public API endpoints.
All endpoints require a valid API key.
"""

import json

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .auth import require_api_key
from .models import CustomEndpoint
from .registry import api_endpoint, get_registered_endpoints


# ── Documentation ────────────────────────────────────────────────

@require_GET
@require_api_key
@api_endpoint("/api/docs", summary="API Documentation", description="Returns the auto-generated API documentation.")
def api_docs(request):
    """Return auto-generated API documentation as JSON."""
    from .models import CustomEndpoint as CE
    endpoints = get_registered_endpoints()

    # Add custom endpoints to docs
    custom = CE.objects.filter(is_active=True)
    for ep in custom:
        endpoints.append({
            "path": ep.full_path,
            "method": "GET",
            "summary": ep.name,
            "description": ep.description,
            "params": [],
            "response_example": None,
            "view_name": "custom_endpoint",
        })

    return JsonResponse({
        "api": "VATéir API",
        "version": "1.0",
        "authentication": {
            "methods": [
                "Authorization: Bearer <api_key>",
                "X-API-Key: <api_key>",
                "Query parameter: ?api_key=<api_key>",
            ],
            "key_format": "vateir_<64 hex chars>",
        },
        "endpoints": [
            {
                "path": ep["path"],
                "method": ep["method"],
                "summary": ep["summary"],
                "description": ep["description"],
                "parameters": ep["params"],
            }
            for ep in endpoints
        ],
    })


# ── Controllers ──────────────────────────────────────────────────

@require_GET
@require_api_key
@api_endpoint(
    "/api/controllers",
    summary="List Controllers",
    description="Returns all controllers on the facility roster.",
    params=[
        {"name": "rating", "in": "query", "description": "Filter by minimum rating", "required": False},
    ],
    response_example={"controllers": [{"cid": 1234567, "name": "John Doe", "rating": 5, "rating_label": "C1"}]},
)
def api_controllers(request):
    from apps.controllers.models import Controller
    qs = Controller.objects.filter(on_roster=True, rating__gte=2)

    min_rating = request.GET.get("rating")
    if min_rating and min_rating.isdigit():
        qs = qs.filter(rating__gte=int(min_rating))

    controllers = []
    for c in qs:
        controllers.append({
            "cid": c.cid,
            "name": f"{c.first_name} {c.last_name}".strip(),
            "rating": c.rating,
            "rating_label": settings.VATSIM_RATINGS.get(c.rating, str(c.rating)),
            "visitor_status": c.visitor_status,
            "on_roster": c.on_roster,
        })

    return JsonResponse({"controllers": controllers})


# ── Online ATC ───────────────────────────────────────────────────

@require_GET
@require_api_key
@api_endpoint(
    "/api/online",
    summary="Online ATC",
    description="Returns currently online controllers in the FIR.",
)
def api_online(request):
    from apps.controllers.models import LiveSession
    sessions = LiveSession.objects.filter(is_active=True)
    data = []
    for s in sessions:
        data.append({
            "cid": s.cid,
            "callsign": s.callsign,
            "frequency": s.frequency,
            "rating": s.rating,
            "logon_time": s.logon_time.isoformat() if s.logon_time else None,
        })
    return JsonResponse({"online": data, "count": len(data)})


# ── Events ───────────────────────────────────────────────────────

@require_GET
@require_api_key
@api_endpoint(
    "/api/events",
    summary="List Events",
    description="Returns upcoming published events.",
    params=[
        {"name": "include_past", "in": "query", "description": "Include past events (true/false)", "required": False},
    ],
)
def api_events(request):
    from apps.events.models import Event
    qs = Event.objects.filter(is_published=True).select_related("airport")

    if request.GET.get("include_past") != "true":
        qs = qs.filter(end_datetime__gte=timezone.now())

    events = []
    for e in qs:
        events.append({
            "id": e.pk,
            "title": e.title,
            "slug": e.slug,
            "description": e.description,
            "airport": e.airport.icao if e.airport else None,
            "start": e.start_datetime.isoformat(),
            "end": e.end_datetime.isoformat(),
            "is_featured": e.is_featured,
            "banner_url": e.banner_display_url,
        })

    return JsonResponse({"events": events})


# ── Airports ─────────────────────────────────────────────────────

@require_GET
@require_api_key
@api_endpoint(
    "/api/airports",
    summary="List Airports",
    description="Returns all visible airports with briefing data.",
)
def api_airports(request):
    from apps.public.models import Airport
    airports = []
    for a in Airport.objects.filter(is_visible=True):
        metar = cache.get(f"metar:{a.icao}", "")
        airports.append({
            "icao": a.icao,
            "name": a.name,
            "latitude": a.latitude,
            "longitude": a.longitude,
            "elevation_ft": a.elevation_ft,
            "metar": metar,
            "staff_notice": a.staff_notice or None,
        })
    return JsonResponse({"airports": airports})


@require_GET
@require_api_key
@api_endpoint(
    "/api/airports/{icao}",
    summary="Airport Detail",
    description="Returns detailed airport information including NOTAMs and runways.",
    params=[
        {"name": "icao", "in": "path", "description": "ICAO code", "required": True},
    ],
)
def api_airport_detail(request, icao):
    from apps.public.models import Airport, NOTAM
    try:
        airport = Airport.objects.get(icao=icao.upper(), is_visible=True)
    except Airport.DoesNotExist:
        return JsonResponse({"error": "Airport not found"}, status=404)

    metar = cache.get(f"metar:{airport.icao}", "")

    runways = []
    for rwy in airport.runways.all():
        runways.append({
            "designator": rwy.designator,
            "heading": rwy.heading,
            "length_m": rwy.length_m,
            "preferential_arrival": rwy.preferential_arrival,
            "preferential_departure": rwy.preferential_departure,
            "max_tailwind_kt": rwy.max_tailwind_kt,
        })

    notams = []
    for n in NOTAM.objects.filter(icao_location__icontains=airport.icao, status__in=["NEW", "REPLACE"]).order_by("-begin_position")[:50]:
        notams.append({
            "notam_number": n.notam_number,
            "status": n.status,
            "raw_text": n.raw_text,
            "begin": n.begin_position.isoformat() if n.begin_position else None,
            "end": n.end_position.isoformat() if n.end_position else None,
        })

    return JsonResponse({
        "airport": {
            "icao": airport.icao,
            "name": airport.name,
            "latitude": airport.latitude,
            "longitude": airport.longitude,
            "elevation_ft": airport.elevation_ft,
            "metar": metar,
            "staff_notice": airport.staff_notice or None,
            "runways": runways,
            "notams": notams,
            "charts": {
                "aerodrome": airport.chart_ad_url or None,
                "ground": airport.chart_ground_url or None,
                "sid": airport.chart_sid_url or None,
                "star": airport.chart_star_url or None,
                "iap": airport.chart_iap_url or None,
                "extra": airport.extra_charts,
            },
        },
    })


# ── METARs ───────────────────────────────────────────────────────

@require_GET
@require_api_key
@api_endpoint(
    "/api/metar/{icao}",
    summary="Get METAR",
    description="Returns the cached METAR for an airport.",
    params=[
        {"name": "icao", "in": "path", "description": "ICAO code", "required": True},
    ],
)
def api_metar(request, icao):
    metar = cache.get(f"metar:{icao.upper()}", "")
    return JsonResponse({"icao": icao.upper(), "metar": metar or None})


# ── Custom Endpoints ─────────────────────────────────────────────

@require_GET
@require_api_key
def serve_custom_endpoint(request, path):
    """Serve a custom endpoint defined in the admin panel."""
    try:
        endpoint = CustomEndpoint.objects.get(path=path, is_active=True)
    except CustomEndpoint.DoesNotExist:
        return JsonResponse({"error": "Endpoint not found"}, status=404)

    return HttpResponse(
        endpoint.response_body,
        content_type=endpoint.content_type,
        status=endpoint.status_code,
    )
