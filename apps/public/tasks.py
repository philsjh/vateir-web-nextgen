"""
Celery tasks for public data: METAR fetching, NOTAM syncing.
"""

import html
import logging

import requests
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

METAR_API_URL = "https://aviationweather.gov/api/data/metar"


@shared_task
def fetch_metars():
    """Fetch METARs for all visible airports and store in Redis cache."""
    from .models import Airport

    icaos = list(Airport.objects.filter(is_visible=True).values_list("icao", flat=True))
    if not icaos:
        return

    for icao in icaos:
        try:
            resp = requests.get(
                METAR_API_URL,
                params={"ids": icao, "format": "raw", "taf": "false"},
                timeout=10,
            )
            resp.raise_for_status()
            metar_text = resp.text.strip()
            if metar_text:
                cache.set(f"metar:{icao}", metar_text, 600)
                logger.debug("Fetched METAR for %s", icao)
        except Exception as exc:
            logger.warning("Failed to fetch METAR for %s: %s", icao, exc)


@shared_task
def fetch_notams():
    """Fetch NOTAMs for all visible airports and store in the database."""
    from .models import Airport, NOTAM

    api_key = getattr(settings, "NOTAM_API_KEY", "")
    if not api_key:
        logger.warning("NOTAM_API_KEY not configured, skipping NOTAM fetch")
        return

    airports = Airport.objects.filter(is_visible=True)
    if not airports.exists():
        return

    headers = {"x-api-key": api_key}
    base_url = getattr(settings, "NOTAM_API_BASE", "https://notams.coredoes.dev/api")

    seen_ids = set()

    for airport in airports:
        try:
            resp = requests.get(
                f"{base_url}/notams",
                params={
                    "icao_location": airport.icao,
                    "active": "true",
                    "limit": 100,
                },
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            notams = resp.json()

            for item in notams:
                nid = item["id"]
                if nid in seen_ids:
                    continue
                seen_ids.add(nid)

                begin = parse_datetime(item.get("begin_position") or "")
                end = parse_datetime(item.get("end_position") or "")

                NOTAM.objects.update_or_create(
                    notam_id=nid,
                    defaults={
                        "notam_number": item.get("notam_number", ""),
                        "icao_location": item.get("icao_location", airport.icao),
                        "status": item.get("status", "NEW"),
                        "raw_text": html.unescape(item.get("raw_text", "")),
                        "icao_text": html.unescape(item.get("icao_text", "")),
                        "latitude": item.get("latitude"),
                        "longitude": item.get("longitude"),
                        "radius_nm": item.get("radius_nm"),
                        "begin_position": begin,
                        "end_position": end,
                    },
                )

            logger.debug("Fetched %d NOTAMs for %s", len(notams), airport.icao)
        except Exception as exc:
            logger.warning("Failed to fetch NOTAMs for %s: %s", airport.icao, exc)

    # Clean up NOTAMs no longer returned as active
    if seen_ids:
        stale = NOTAM.objects.filter(status__in=["NEW", "REPLACE"]).exclude(notam_id__in=seen_ids)
        stale.update(status="CANCELLED")
