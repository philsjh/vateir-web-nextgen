import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.controllers.models import Controller, ATCSession
from .airspace import point_in_polygon, lat_lon_to_radar, get_sector_svg_points, get_airport_radar_positions, format_altitude
from .models import StaffMember, InfoPage

logger = logging.getLogger(__name__)


def _get_vatsim_data():
    """Fetch and cache the full VATSIM data feed (30s TTL)."""
    cached = cache.get("vatsim_data_feed")
    if cached is not None:
        return cached

    try:
        resp = requests.get(settings.VATSIM_DATA_FEED, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cache.set("vatsim_data_feed", data, 30)
        return data
    except Exception as exc:
        logger.warning("Failed to fetch VATSIM data feed: %s", exc)
        return {}


def _get_callsign_re():
    """Get compiled callsign regex for our FIR prefixes."""
    pattern = cache.get("homepage_callsign_regex")
    if pattern is not None:
        return pattern
    try:
        from apps.accounts.models import SiteConfig
        pattern = SiteConfig.get().get_callsign_regex()
    except Exception:
        pattern = re.compile(r"^EI[A-Z0-9_]{2,}", re.IGNORECASE)
    cache.set("homepage_callsign_regex", pattern, 300)
    return pattern


def _get_live_atc(data):
    """Extract controllers matching our FIR callsign prefixes from the VATSIM data feed."""
    callsign_re = _get_callsign_re()
    controllers = []
    for entry in data.get("controllers", []):
        callsign = entry.get("callsign", "")
        if not callsign_re.match(callsign):
            continue
        rating_int = entry.get("rating", 1)
        rating_label = settings.VATSIM_RATINGS.get(rating_int, str(rating_int))
        controllers.append({
            "callsign": callsign,
            "cid": entry.get("cid", ""),
            "frequency": entry.get("frequency", ""),
            "rating": rating_label,
            "logon_time": entry.get("logon_time", ""),
        })
    return controllers


def _get_radar_traffic(data):
    """Extract pilots currently in Irish airspace with flight plan info."""
    traffic = []
    for pilot in data.get("pilots", []):
        lat = pilot.get("latitude")
        lon = pilot.get("longitude")
        if lat is None or lon is None:
            continue

        if not point_in_polygon(lat, lon):
            continue

        x, y = lat_lon_to_radar(lat, lon)

        # Extract flight plan departure/destination
        fp = pilot.get("flight_plan") or {}
        departure = fp.get("departure", "")
        arrival = fp.get("arrival", "")

        alt_feet = pilot.get("altitude", 0)
        traffic.append({
            "callsign": pilot.get("callsign", ""),
            "x": x,
            "y": y,
            "altitude": format_altitude(alt_feet),
            "groundspeed": pilot.get("groundspeed", 0),
            "heading": pilot.get("heading", 0),
            "departure": departure,
            "arrival": arrival,
        })

    return traffic[:30]


def _get_metars():
    """Fetch METARs directly. Try cache first, then fetch from aviationweather.gov."""
    try:
        from apps.accounts.models import SiteConfig
        config = SiteConfig.get()
        icaos = config.get_metar_icaos()
    except Exception:
        icaos = ["EIDW", "EINN", "EICK"]

    metars = {}
    missing = []
    for icao in icaos:
        cached = cache.get(f"metar:{icao}")
        if cached:
            metars[icao] = cached
        else:
            missing.append(icao)

    if missing:
        # Fetch all missing in one request
        try:
            ids = ",".join(missing)
            resp = requests.get(
                "https://aviationweather.gov/api/data/metar",
                params={"ids": ids, "format": "raw", "taf": "false"},
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.text.strip()
            # Response may have "METAR EIDW ..." format, one per line
            # We want the most recent (first) METAR for each station
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                for icao in missing:
                    if icao in line and icao not in metars:
                        # Strip "METAR " prefix if present
                        metar_text = line
                        if metar_text.startswith("METAR "):
                            metar_text = metar_text[6:]
                        metars[icao] = metar_text
                        cache.set(f"metar:{icao}", metar_text, 300)
                        break
        except Exception as exc:
            logger.warning("Failed to fetch METARs: %s", exc)

    # Return in the original order
    return {icao: metars[icao] for icao in icaos if icao in metars}


def homepage(request):
    # Fetch VATSIM data once
    vatsim_data = _get_vatsim_data()

    # Live ATC from data feed
    live_atc = _get_live_atc(vatsim_data)

    # METARs
    metars = _get_metars()

    # Basic stats
    total_controllers = Controller.objects.filter(is_active=True).count()
    total_sessions = ATCSession.objects.count()

    # Upcoming events
    from apps.events.models import Event
    upcoming_events = Event.objects.filter(
        is_published=True, start_datetime__gte=timezone.now()
    ).order_by("start_datetime")[:3]

    # Radar traffic
    radar_traffic = _get_radar_traffic(vatsim_data)

    # Sector outline for SVG
    sector_svg_points = get_sector_svg_points(320)

    # Reference airports for radar
    radar_airports = get_airport_radar_positions()

    context = {
        "live_atc": live_atc,
        "metars": metars,
        "total_controllers": total_controllers,
        "total_sessions": total_sessions,
        "upcoming_events": upcoming_events,
        "radar_traffic": radar_traffic,
        "sector_svg_points": sector_svg_points,
        "radar_airports": radar_airports,
    }
    return render(request, "public/homepage.html", context)


def staff_page(request):
    staff = StaffMember.objects.filter(is_active=True)
    return render(request, "public/staff.html", {"staff_members": staff})


def info_page(request, slug):
    page = get_object_or_404(InfoPage, slug=slug, is_published=True)
    return render(request, "public/info_page.html", {"page": page})
