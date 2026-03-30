"""
Celery tasks for public data: METAR fetching.
"""

import logging

import requests
from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)

METAR_API_URL = "https://aviationweather.gov/api/data/metar"


@shared_task
def fetch_metars():
    """Fetch METARs for configured airports and store in Redis cache."""
    try:
        from apps.accounts.models import SiteConfig
        config = SiteConfig.get()
        icaos = config.get_metar_icaos()
    except Exception:
        icaos = ["EIDW", "EINN", "EICK"]

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
