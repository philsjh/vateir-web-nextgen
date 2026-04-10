"""
Runway selection logic.

Determines the active runway from:
  1. ATIS text (highest priority — read from live VATSIM data)
  2. Wind analysis against defined runways and preferential rules
"""

import math
import re


def parse_wind_from_metar(metar_text: str) -> tuple[int | None, int | None, int | None]:
    """
    Extract wind direction, speed, and gust from a METAR string.
    Returns (direction_deg, speed_kt, gust_kt) or (None, None, None).

    Handles: 17017G28KT, 24005KT, VRB03KT, 00000KT
    """
    if not metar_text:
        return None, None, None

    match = re.search(r"\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b", metar_text)
    if not match:
        return None, None, None

    direction_str, speed_str, gust_str = match.groups()

    if direction_str == "VRB":
        return None, int(speed_str), int(gust_str) if gust_str else None

    return int(direction_str), int(speed_str), int(gust_str) if gust_str else None


def wind_component(wind_dir: int, wind_speed: int, runway_heading: int) -> tuple[float, float]:
    """
    Calculate headwind and crosswind components for a runway.
    Returns (headwind_kt, crosswind_kt).

    Positive headwind = into the wind (good).
    Negative headwind = tailwind (bad).
    """
    angle_rad = math.radians(wind_dir - runway_heading)
    headwind = wind_speed * math.cos(angle_rad)
    crosswind = abs(wind_speed * math.sin(angle_rad))
    return round(headwind, 1), round(crosswind, 1)


def parse_runway_from_atis(atis_lines: list[str]) -> dict | None:
    """
    Parse landing and takeoff runways from ATIS text.

    Handles formats like:
      LDG RWY 16, TKOF RWY 16
      LDG RWY 28R, TKOF RWY 28L
      ARR RWY 10, DEP RWY 10

    Returns dict with 'landing' and 'takeoff' keys, or None.
    """
    if not atis_lines:
        return None

    full_text = " ".join(atis_lines).upper()

    result = {}

    # Landing runway
    ldg = re.search(r"(?:LDG|LANDING|ARR)\s*(?:RWY|RUNWAY)\s*(\d{1,2}[LRC]?)", full_text)
    if ldg:
        result["landing"] = ldg.group(1)

    # Takeoff runway
    tko = re.search(r"(?:TKOF|TAKEOFF|DEP)\s*(?:RWY|RUNWAY)\s*(\d{1,2}[LRC]?)", full_text)
    if tko:
        result["takeoff"] = tko.group(1)

    return result if result else None


def determine_active_runway(
    runways,
    metar_text: str | None = None,
    atis_lines: list[str] | None = None,
) -> dict:
    """
    Determine the active runway for an airport.

    Priority:
      1. ATIS text (if an ATIS controller is online)
      2. Wind-based analysis using preferential runway rules
      3. Fallback to first preferential runway

    Returns dict:
      {
        "source": "atis" | "wind" | "preferential" | "none",
        "landing": "28L",
        "takeoff": "28R",
        "atis_info": "E",  # ATIS letter if from ATIS
        "wind_dir": 270,
        "wind_speed": 15,
        "wind_gust": None,
        "analysis": [
          {"runway": "28L", "headwind": 14.2, "crosswind": 3.1, "suitable": True},
          ...
        ]
      }
    """
    result = {
        "source": "none",
        "landing": None,
        "takeoff": None,
        "atis_info": None,
        "wind_dir": None,
        "wind_speed": None,
        "wind_gust": None,
        "analysis": [],
    }

    if not runways:
        return result

    # Parse wind from METAR
    wind_dir, wind_speed, wind_gust = parse_wind_from_metar(metar_text)
    result["wind_dir"] = wind_dir
    result["wind_speed"] = wind_speed
    result["wind_gust"] = wind_gust

    # 1. Try ATIS first
    if atis_lines:
        atis_rwy = parse_runway_from_atis(atis_lines)
        if atis_rwy:
            result["source"] = "atis"
            result["landing"] = atis_rwy.get("landing")
            result["takeoff"] = atis_rwy.get("takeoff") or atis_rwy.get("landing")

            # Extract ATIS letter
            full_text = " ".join(atis_lines).upper()
            info_match = re.search(r"ATIS\s+(?:INFO(?:RMATION)?\s+)?([A-Z])\b", full_text)
            if info_match:
                result["atis_info"] = info_match.group(1)

    # 2. Wind analysis for all runways (always compute for display)
    if wind_dir is not None and wind_speed is not None:
        for rwy in runways:
            headwind, crosswind = wind_component(wind_dir, wind_speed, rwy.heading)
            tailwind = -headwind if headwind < 0 else 0

            is_pref_arr = rwy.preferential_arrival
            is_pref_dep = rwy.preferential_departure
            is_pref = is_pref_arr or is_pref_dep

            # Preferential runways: suitable if tailwind within their limit
            # Non-preferential runways: only used as fallback — marked suitable
            #   but only selected when preferential runways are out of limits
            if is_pref:
                suitable = tailwind <= rwy.max_tailwind_kt
            else:
                suitable = headwind >= 0

            result["analysis"].append({
                "runway": rwy.designator,
                "heading": rwy.heading,
                "headwind": headwind,
                "crosswind": crosswind,
                "tailwind": tailwind,
                "suitable": suitable,
                "pref_arrival": is_pref_arr,
                "pref_departure": is_pref_dep,
            })

        # If no ATIS, pick the best runway from wind
        if result["source"] == "none":
            all_analysis = result["analysis"]

            def _pick_runway(pref_key):
                """Pick best runway: preferential first, non-preferential only
                when all preferential are out of limits or crosswind > 20kt."""
                pref = [a for a in all_analysis if a[pref_key] and a["suitable"]]
                if pref:
                    return max(pref, key=lambda a: a["headwind"])["runway"]

                # All preferential runways are out of limits — fall back to
                # non-preferential runways, but only consider those that are
                # into wind (suitable) or where crosswind on preferential > 20kt
                pref_xwind_exceeded = any(
                    a["crosswind"] > 20 for a in all_analysis if a[pref_key]
                )
                pref_all_out = not any(
                    a["suitable"] for a in all_analysis if a[pref_key]
                )

                if pref_all_out or pref_xwind_exceeded:
                    fallback = [a for a in all_analysis if a["suitable"]]
                    if fallback:
                        return max(fallback, key=lambda a: a["headwind"])["runway"]
                return None

            result["landing"] = _pick_runway("pref_arrival")
            result["takeoff"] = _pick_runway("pref_departure")

            if result["landing"] or result["takeoff"]:
                result["source"] = "wind"

    # 3. Fallback to preferential
    if result["landing"] is None:
        pref_arr = [rwy for rwy in runways if rwy.preferential_arrival]
        if pref_arr:
            result["source"] = "preferential"
            result["landing"] = pref_arr[0].designator
        else:
            pref_any = [rwy for rwy in runways if rwy.preferential_departure]
            if pref_any:
                result["source"] = "preferential"
                result["landing"] = pref_any[0].designator

    if result["takeoff"] is None:
        pref_dep = [rwy for rwy in runways if rwy.preferential_departure]
        if pref_dep:
            result["takeoff"] = pref_dep[0].designator
        elif result["landing"]:
            result["takeoff"] = result["landing"]

    return result
