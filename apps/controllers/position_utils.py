"""
Callsign parsing logic for Irish positions.
"""


def detect_position_type(callsign: str) -> str:
    cs = callsign.upper()
    if cs.endswith("_DEL"):
        return "DELIVERY"
    if cs.endswith("_GND"):
        return "GROUND"
    if cs.endswith("_TWR"):
        return "TOWER"
    if cs.endswith("_APP"):
        return "APPROACH"
    if cs.endswith("_CTR"):
        return "ACC"
    return ""


def detect_airport_icao(callsign: str) -> str:
    """Extract airport ICAO from callsign like EIDW_TWR -> EIDW."""
    parts = callsign.upper().split("_")
    if parts and len(parts[0]) == 4 and parts[0].startswith("EI"):
        return parts[0]
    return ""


def detect_is_home(callsign: str) -> bool:
    from django.core.cache import cache
    from django.conf import settings
    prefixes = cache.get("home_callsign_prefixes")
    if prefixes is None:
        try:
            from apps.accounts.models import SiteConfig
            prefixes = SiteConfig.get().get_callsign_prefixes()
        except Exception:
            prefixes = settings.DEFAULT_CALLSIGN_PREFIXES.split(",")
            prefixes = [p.strip() for p in prefixes if p.strip()]
        cache.set("home_callsign_prefixes", prefixes, 300)
    cs = callsign.upper()
    return any(cs.startswith(p) for p in prefixes)


def get_or_create_position(callsign: str):
    from .models import Position

    base = callsign.upper().replace("__", "_", 1)
    position, _ = Position.objects.get_or_create(
        callsign=base,
        defaults={
            "position_type": detect_position_type(base),
            "airport_icao": detect_airport_icao(base),
            "is_home": detect_is_home(base),
        },
    )
    return position
