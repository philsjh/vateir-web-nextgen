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

from .models import Controller, BackfillStatus, ATCSession, LiveSession, ControllerStats, Endorsement, EndorsementType, VisitorRequest, VisitorRequestStatus
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


def _get_or_create_controller(cid: int, visitor_status="APPROVED"):
    """Get or create a controller record. For visitors/endorsed controllers
    that don't exist yet, look them up via the VATSIM API."""
    controller = _get_controller(cid)
    if controller:
        return controller

    # Look up via VATSIM API to get their name and rating
    try:
        url = _MEMBER_URL.format(base=settings.VATSIM_API_BASE, cid=cid)
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        member = resp.json()
        controller = Controller.objects.create(
            cid=cid,
            first_name=member.get("name_first", ""),
            last_name=member.get("name_last", ""),
            rating=member.get("rating", 1),
            is_active=True,
            visitor_status=visitor_status,
        )
        logger.info("Created controller CID %s as %s via VATSIM lookup", cid, visitor_status)
        return controller
    except Exception as exc:
        logger.warning("Failed to look up CID %s for controller creation: %s", cid, exc)
        # Create with minimal info
        controller = Controller.objects.create(
            cid=cid,
            rating=1,
            is_active=True,
            visitor_status=visitor_status,
        )
        return controller


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


_MEMBER_URL = "{base}/members/{cid}"
_SUBDIVISION_ROSTER_URL = "{base}/orgs/subdivision/{sub}"


def _vatsim_api_headers():
    """Return auth headers for the VATSIM v2 API."""
    key = getattr(settings, "VATSIM_API_KEY", "")
    if key:
        return {"X-API-KEY": key}
    return {}


def _vateud_api_headers():
    """Return auth headers for the VATEUD Core API."""
    key = getattr(settings, "VATEUD_API_KEY", "")
    if key:
        return {"X-API-KEY": key}
    return {}


_ENDORSEMENT_ENDPOINTS = [
    (EndorsementType.SOLO, "/facility/endorsements/solo"),
    (EndorsementType.TIER_1, "/facility/endorsements/tier-1"),
    (EndorsementType.TIER_2, "/facility/endorsements/tier-2"),
]


def _sync_endorsements(base_url, headers):
    """Fetch and upsert endorsements from all three VATEUD endpoints.

    Returns (added, removed) where each is a list of (type_label, position, cid) tuples.
    """
    added = []
    removed = []

    for etype, path in _ENDORSEMENT_ENDPOINTS:
        try:
            resp = requests.get(f"{base_url}{path}", headers=headers, timeout=30)
            resp.raise_for_status()
            items = resp.json()
        except Exception as exc:
            logger.warning("VATEUD sync: failed to fetch %s: %s", path, exc)
            continue

        if not isinstance(items, list):
            items = items.get("data", [])

        api_ids = set()
        for item in items:
            vateud_id = item.get("id")
            if vateud_id is None:
                continue
            api_ids.add(vateud_id)
            cid = item.get("user_cid")
            controller = _get_or_create_controller(cid) if cid else None

            defaults = {
                "cid": cid,
                "controller": controller,
                "position": item.get("position", ""),
                "instructor_cid": item.get("instructor_cid", 0),
                "facility": item.get("facility", 0),
                "created_at": _parse_dt(item.get("created_at")) or timezone.now(),
                "updated_at": _parse_dt(item.get("updated_at")) or timezone.now(),
            }
            if etype == EndorsementType.SOLO:
                defaults["expires_at"] = _parse_dt(item.get("expiry"))
                defaults["max_days"] = item.get("max_days")

            _, created = Endorsement.objects.update_or_create(
                vateud_id=vateud_id, type=etype, defaults=defaults,
            )
            if created:
                added.append((etype.label, item.get("position", ""), cid))

        # Remove endorsements of this type no longer in the API
        stale = Endorsement.objects.filter(type=etype).exclude(vateud_id__in=api_ids)
        for e in stale:
            removed.append((e.get_type_display(), e.position, e.cid))
        stale.delete()

    return added, removed


def _sync_visitor_requests(base_url, headers):
    """Fetch and upsert pending visitor requests from VATEUD.

    Returns a list of CIDs for newly created requests.
    """
    try:
        resp = requests.get(f"{base_url}/facility/visitors", headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("VATEUD sync: failed to fetch visitor requests: %s", exc)
        return []

    items = data.get("data", []) if isinstance(data, dict) else data
    new_cids = []
    api_ids = set()

    for item in items:
        vateud_id = item.get("id")
        if vateud_id is None:
            continue
        api_ids.add(vateud_id)
        cid = item.get("user_cid")
        controller = _get_or_create_controller(cid, visitor_status="PENDING") if cid else None

        _, created = VisitorRequest.objects.update_or_create(
            vateud_id=vateud_id,
            defaults={
                "cid": cid,
                "controller": controller,
                "reason": item.get("reason", ""),
                "status": VisitorRequestStatus.PENDING,
                "created_at": _parse_dt(item.get("created_at")) or timezone.now(),
                "updated_at": _parse_dt(item.get("updated_at")) or timezone.now(),
            },
        )
        if created:
            new_cids.append(cid)
            # Update Controller.visitor_status to PENDING if currently NONE
            if controller and controller.visitor_status == "NONE":
                controller.visitor_status = "PENDING"
                controller.save(update_fields=["visitor_status", "updated_at"])

    # Requests that disappeared from API — mark as approved
    disappeared = VisitorRequest.objects.filter(
        status=VisitorRequestStatus.PENDING,
    ).exclude(vateud_id__in=api_ids)
    for vr in disappeared:
        vr.status = VisitorRequestStatus.APPROVED
        vr.save(update_fields=["status", "synced_at"])
        # Update Controller.visitor_status if currently PENDING
        if vr.controller and vr.controller.visitor_status == "PENDING":
            vr.controller.visitor_status = "APPROVED"
            vr.controller.save(update_fields=["visitor_status", "updated_at"])

    return new_cids


def _sync_roster_crossref(base_url, headers):
    """Sync the VATEUD facility roster — sets on_roster flag on controllers.

    Controllers on the VATEUD roster get on_roster=True.
    Controllers not on the VATEUD roster get on_roster=False.
    Creates local records for CIDs on the VATEUD roster that don't exist locally.

    Returns dict with 'in_vateud_not_local' and 'in_local_not_vateud' CID lists.
    """
    try:
        resp = requests.get(f"{base_url}/facility/roster", headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("VATEUD sync: failed to fetch roster: %s", exc)
        return {"in_vateud_not_local": [], "in_local_not_vateud": []}

    vateud_cids = set()
    for cid in data.get("controllers", []):
        if isinstance(cid, int):
            vateud_cids.add(cid)
        elif isinstance(cid, dict):
            c = cid.get("cid") or cid.get("id")
            if c:
                vateud_cids.add(int(c))

    if not vateud_cids:
        logger.warning("VATEUD roster: no CIDs returned, skipping flag update")
        return {"in_vateud_not_local": [], "in_local_not_vateud": []}

    local_cids = set(
        Controller.objects.values_list("cid", flat=True)
    )

    in_vateud_not_local = sorted(vateud_cids - local_cids)
    in_local_not_vateud = sorted(
        Controller.objects.filter(on_roster=True).exclude(cid__in=vateud_cids).values_list("cid", flat=True)
    )

    # Create local records for CIDs on the roster that we don't have yet
    for cid in in_vateud_not_local:
        _get_or_create_controller(cid, visitor_status="NONE")

    # Flag everyone on the VATEUD roster
    Controller.objects.filter(cid__in=vateud_cids).update(on_roster=True)
    # Unflag everyone not on the VATEUD roster
    Controller.objects.exclude(cid__in=vateud_cids).update(on_roster=False)

    logger.info(
        "VATEUD roster sync: %d on roster, %d new, %d removed",
        len(vateud_cids), len(in_vateud_not_local), len(in_local_not_vateud),
    )

    return {
        "in_vateud_not_local": in_vateud_not_local,
        "in_local_not_vateud": in_local_not_vateud,
    }


@shared_task
def sync_vateud():
    """
    Sync endorsements, visitor requests, and roster cross-reference
    from the VATEUD Core API.
    """
    headers = _vateud_api_headers()
    if not headers:
        logger.warning("VATEUD sync: VATEUD_API_KEY not set, skipping")
        return

    base_url = getattr(settings, "VATEUD_API_BASE", "https://api-core.vateud.net")

    endorsements_added, endorsements_removed = _sync_endorsements(base_url, headers)
    new_visitor_requests = _sync_visitor_requests(base_url, headers)
    roster_discrepancies = _sync_roster_crossref(base_url, headers)

    logger.info(
        "VATEUD sync complete: %d endorsements added, %d removed, %d new visitor requests",
        len(endorsements_added), len(endorsements_removed), len(new_visitor_requests),
    )

    try:
        from apps.notifications.discord import notify_vateud_sync
        notify_vateud_sync(
            endorsements_added=endorsements_added,
            endorsements_removed=endorsements_removed,
            new_visitor_requests=new_visitor_requests,
            roster_discrepancies=roster_discrepancies,
        )
    except Exception as exc:
        logger.warning("VATEUD sync Discord notification failed: %s", exc)


@shared_task
def sync_roster():
    """
    Sync the full subdivision roster from the VATSIM v2 API.
    Tracks changes (new members, rating changes, departures) and
    reports them via Discord.
    """
    subdivision = getattr(settings, "VATSIM_SUBDIVISION", "IRL")
    headers = _vatsim_api_headers()
    if not headers:
        logger.warning("Roster sync: VATSIM_API_KEY not set, skipping")
        return

    url = _SUBDIVISION_ROSTER_URL.format(base=settings.VATSIM_API_BASE, sub=subdivision)
    page = 1
    created = 0
    updated = 0

    # Track changes for Discord notification
    new_members = []
    rating_changes = []
    api_cids = set()

    while True:
        try:
            resp = requests.get(url, headers=headers, params={"page": page, "limit": 500}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("Roster sync: API error on page %d: %s", page, exc)
            break

        items = data if isinstance(data, list) else data.get("items", data.get("data", []))
        if not items:
            break

        for member in items:
            cid = member.get("id") or member.get("cid")
            if not cid:
                continue
            cid = int(cid)
            api_cids.add(cid)
            rating = member.get("rating", 1)
            first_name = member.get("name_first", "")
            last_name = member.get("name_last", "")
            email = member.get("email", "")
            display_name = f"{first_name} {last_name}".strip() or str(cid)

            controller, is_new = Controller.objects.get_or_create(
                cid=cid,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "rating": rating,
                    "is_active": True,
                    "visitor_status": "NONE",
                },
            )
            if not is_new:
                changed = False
                update_fields = []

                # Track rating changes
                if controller.rating != rating:
                    old_label = settings.VATSIM_RATINGS.get(controller.rating, str(controller.rating))
                    new_label = settings.VATSIM_RATINGS.get(rating, str(rating))
                    rating_changes.append((display_name, old_label, new_label))
                    controller.rating = rating
                    changed = True
                    update_fields.append("rating")

                if controller.visitor_status != "NONE":
                    controller.visitor_status = "NONE"
                    changed = True
                    update_fields.append("visitor_status")
                if not controller.is_active:
                    controller.is_active = True
                    changed = True
                    update_fields.append("is_active")
                if first_name and controller.first_name != first_name:
                    controller.first_name = first_name
                    changed = True
                    update_fields.append("first_name")
                if last_name and controller.last_name != last_name:
                    controller.last_name = last_name
                    changed = True
                    update_fields.append("last_name")
                if email and controller.email != email:
                    controller.email = email
                    changed = True
                    update_fields.append("email")
                if changed:
                    update_fields.append("updated_at")
                    controller.save(update_fields=update_fields)
                    updated += 1
            else:
                created += 1
                new_members.append(display_name)

        # Pagination
        total = data.get("count", data.get("total", 0)) if isinstance(data, dict) else 0
        if total and page * 500 < total:
            page += 1
        elif isinstance(data, list) and len(items) == 500:
            page += 1
        else:
            break

    # Detect departures: home controllers no longer in the API response
    # Only deactivate — don't change visitor_status (visitors are handled by sync_vateud)
    removed = 0
    departed = []
    if api_cids:
        departed_controllers = Controller.objects.filter(
            visitor_status="NONE", is_active=True,
        ).exclude(cid__in=api_cids)
        for c in departed_controllers:
            c.is_active = False
            c.save(update_fields=["is_active", "updated_at"])
            departed.append(f"{c.first_name} {c.last_name}".strip() or str(c.cid))
            removed += 1

    logger.info(
        "Roster sync complete: %d created, %d updated, %d departed",
        created, updated, removed,
    )

    # Send Discord notification
    try:
        from apps.notifications.discord import notify_roster_sync
        notify_roster_sync(
            created=created,
            updated=updated,
            removed=removed,
            new_members=new_members,
            rating_changes=rating_changes,
            departed=departed,
        )
    except Exception as exc:
        logger.warning("Roster sync Discord notification failed: %s", exc)


@shared_task
def lookup_and_register_controller(cid: int):
    """Look up a single CID via VATSIM API and register them if not already known."""
    if Controller.objects.filter(pk=cid).exists():
        return

    try:
        url = _MEMBER_URL.format(base=settings.VATSIM_API_BASE, cid=cid)
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        member = resp.json()
    except Exception as exc:
        logger.warning("Failed to look up CID %s: %s", cid, exc)
        return

    subdivision = getattr(settings, "VATSIM_SUBDIVISION", "IRL")
    is_home = member.get("subdivision_id", "") == subdivision
    Controller.objects.create(
        cid=cid,
        rating=member.get("rating", 1),
        is_active=True,
        visitor_status="NONE" if is_home else "APPROVED",
    )
    logger.info("Registered CID %s via lookup (home=%s)", cid, is_home)
