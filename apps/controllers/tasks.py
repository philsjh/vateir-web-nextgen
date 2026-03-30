"""
Celery tasks for session tracking and controller stats.
"""

import logging
import re
from datetime import timedelta

import requests
from celery import group, shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import Controller, BackfillStatus, ATCSession, LiveSession, ControllerStats
from .position_utils import get_or_create_position

logger = logging.getLogger(__name__)

_ATC_HISTORY_URL = "{base}/members/{cid}/atc"
_STATS_URL = "{base}/members/{cid}/stats"
_PAGE_SIZE = 2000


def _get_callsign_re():
    pattern = cache.get("callsign_regex")
    if pattern is None:
        try:
            from apps.accounts.models import SiteConfig
            pattern = SiteConfig.get().get_callsign_regex()
        except Exception:
            pattern = re.compile(r"^EI[A-Z0-9_]{2,}", re.IGNORECASE)
        cache.set("callsign_regex", pattern, 300)
    return pattern


def _parse_dt(s: str):
    if not s:
        return None
    from django.utils.dateparse import parse_datetime
    try:
        dt = parse_datetime(s)
        if dt and dt.tzinfo is None:
            from django.utils.timezone import make_aware
            dt = make_aware(dt)
        return dt
    except Exception:
        return None


def _get_controller(cid: int):
    try:
        return Controller.objects.get(pk=cid)
    except Controller.DoesNotExist:
        return None


@shared_task
def poll_live_feed():
    """
    Fetch the VATSIM data feed, match controllers on tracked callsigns,
    and upsert LiveSession rows.
    """
    try:
        resp = requests.get(settings.VATSIM_DATA_FEED, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch VATSIM data feed: %s", exc)
        return

    now = timezone.now()
    active_keys: dict[tuple, bool] = {}

    for entry in data.get("controllers", []):
        callsign = entry.get("callsign", "")
        if not _get_callsign_re().match(callsign):
            continue

        cid = int(entry["cid"])
        logon_str = entry.get("logon_time", "")
        logon_time = _parse_dt(logon_str) or now

        get_or_create_position(callsign)
        controller = _get_controller(cid)

        session_key = (cid, callsign)
        active_keys[session_key] = True

        live, created = LiveSession.objects.get_or_create(
            cid=cid,
            callsign=callsign,
            is_active=True,
            defaults={
                "controller": controller,
                "frequency": entry.get("frequency", ""),
                "facility": entry.get("facility", 0),
                "rating": entry.get("rating", 1),
                "server": entry.get("server", ""),
                "logon_time": logon_time,
                "last_seen": now,
            },
        )
        if not created:
            live.last_seen = now
            live.controller = controller
            live.save(update_fields=["last_seen", "controller"])

    grace_period = timedelta(seconds=60)
    stale = LiveSession.objects.filter(is_active=True)
    for session in stale:
        key = (session.cid, session.callsign)
        if key not in active_keys:
            if now - session.last_seen >= grace_period:
                session.is_active = False
                session.ended_at = session.last_seen
                session.save(update_fields=["is_active", "ended_at"])
                logger.info("Session ended: %s (CID %s)", session.callsign, session.cid)

    cache.set("last_live_poll", now, timeout=None)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def backfill_controller_sessions(self, cid: int):
    """Paginate through the VATSIM ATC history API and import sessions."""
    try:
        controller = Controller.objects.get(pk=cid)
    except Controller.DoesNotExist:
        logger.warning("Backfill requested for unknown CID %s", cid)
        return

    backfill_years = getattr(settings, "BACKFILL_YEARS", 0)
    cutoff = None
    if backfill_years > 0:
        cutoff = timezone.now() - timedelta(days=365 * backfill_years)

    controller.backfill_status = BackfillStatus.IN_PROGRESS
    controller.backfill_started_at = timezone.now()
    controller.save(update_fields=["backfill_status", "backfill_started_at"])

    url = _ATC_HISTORY_URL.format(base=settings.VATSIM_API_BASE, cid=cid)
    page_num = 1
    imported = 0
    stop = False

    while not stop:
        try:
            resp = requests.get(url, params={"page": page_num, "limit": _PAGE_SIZE}, timeout=60)
            resp.raise_for_status()
            page = resp.json()
        except Exception as exc:
            logger.error("Backfill fetch error for CID %s page %s: %s", cid, page_num, exc)
            controller.backfill_status = BackfillStatus.FAILED
            controller.save(update_fields=["backfill_status"])
            raise self.retry(exc=exc)

        items = page.get("items", [])
        total = page.get("count", 0)
        if not items:
            break

        for item in items:
            conn = item.get("connection_id", {})
            start_dt = _parse_dt(conn.get("start"))
            end_dt = _parse_dt(conn.get("end"))

            if not start_dt or not end_dt:
                continue

            if cutoff and start_dt < cutoff:
                stop = True
                break

            connection_id = conn.get("id")
            if connection_id is None:
                continue

            session_callsign = conn.get("callsign", "")
            ATCSession.objects.update_or_create(
                connection_id=connection_id,
                defaults={
                    "cid": int(conn.get("vatsim_id", cid)),
                    "controller": controller,
                    "callsign": session_callsign,
                    "position": get_or_create_position(session_callsign) if session_callsign else None,
                    "rating": conn.get("rating", 1),
                    "start": start_dt,
                    "end": end_dt,
                    "server": conn.get("server", ""),
                    "aircraft_tracked": item.get("aircrafttracked", 0),
                    "aircraft_seen": item.get("aircraftseen", 0),
                    "flights_amended": item.get("flightsamended", 0),
                    "handoffs_initiated": item.get("handoffsinitiated", 0),
                    "handoffs_received": item.get("handoffsreceived", 0),
                    "handoffs_refused": item.get("handoffsrefused", 0),
                    "squawks_assigned": item.get("squawksassigned", 0),
                    "cruise_alts_modified": item.get("cruisealtsmodified", 0),
                    "temp_alts_modified": item.get("tempaltsmodified", 0),
                    "scratchpad_mods": item.get("scratchpadmods", 0),
                    "is_backfilled": True,
                },
            )
            imported += 1

        fetched_so_far = page_num * len(items)
        if total > fetched_so_far:
            page_num += 1
        else:
            break

    controller.backfill_status = BackfillStatus.COMPLETE
    controller.backfill_completed_at = timezone.now()
    controller.save(update_fields=["backfill_status", "backfill_completed_at"])
    logger.info("Backfill complete for CID %s: %d imported", cid, imported)


@shared_task
def backfill_all_controllers():
    """Fan-out: trigger backfill for every active controller."""
    cids = list(Controller.objects.filter(is_active=True).values_list("cid", flat=True))
    if not cids:
        return
    job = group(backfill_controller_sessions.s(cid) for cid in cids)
    job.apply_async()
    logger.info("Queued backfill for %d controllers", len(cids))


@shared_task
def update_all_controller_stats():
    """Update cached stats for all active controllers from VATSIM API."""
    controllers = Controller.objects.filter(is_active=True)
    for controller in controllers:
        try:
            url = _STATS_URL.format(base=settings.VATSIM_API_BASE, cid=controller.cid)
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            ControllerStats.objects.update_or_create(
                controller=controller,
                defaults={
                    "atc": data.get("atc", 0),
                    "pilot": data.get("pilot", 0),
                    "s1": data.get("s1", 0),
                    "s2": data.get("s2", 0),
                    "s3": data.get("s3", 0),
                    "c1": data.get("c1", 0),
                    "c2": data.get("c2", 0),
                    "c3": data.get("c3", 0),
                    "i1": data.get("i1", 0),
                    "i2": data.get("i2", 0),
                    "i3": data.get("i3", 0),
                    "sup": data.get("sup", 0),
                    "adm": data.get("adm", 0),
                    "last_updated": timezone.now(),
                },
            )
        except Exception as exc:
            logger.warning("Failed to update stats for CID %s: %s", controller.cid, exc)
