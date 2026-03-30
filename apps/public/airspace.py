"""
Airspace polygon utilities for checking if aircraft are in Irish FIR.
"""

import re
from pathlib import Path

_BBOX = None
_POLYGON = None

# Reference airports for the radar display
REFERENCE_AIRPORTS = [
    {"icao": "EIDW", "name": "Dublin", "lat": 53.4213, "lon": -6.2701},
    {"icao": "EINN", "name": "Shannon", "lat": 52.7019, "lon": -8.9248},
    {"icao": "EICK", "name": "Cork", "lat": 51.8413, "lon": -8.4911},
    {"icao": "EIDL", "name": "Donegal", "lat": 55.0442, "lon": -8.3410},
]


def _parse_coord(s: str) -> float:
    """Parse 'N054.43.00.000' or 'W010.00.00.000' to decimal degrees."""
    m = re.match(r"([NSEW])(\d+)\.(\d+)\.(\d+)\.(\d+)", s.strip())
    if not m:
        raise ValueError(f"Cannot parse coordinate: {s}")
    direction, deg, minutes, sec, frac = m.groups()
    decimal = int(deg) + int(minutes) / 60 + (int(sec) + int(frac) / 1000) / 3600
    if direction in ("S", "W"):
        decimal = -decimal
    return decimal


def _load_polygon():
    """Load the airspace polygon from data/airspace_polygon.txt."""
    global _POLYGON, _BBOX
    if _POLYGON is not None:
        return _POLYGON

    polygon_file = Path(__file__).resolve().parent.parent.parent / "data" / "airspace_polygon.txt"
    points = []
    for line in polygon_file.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) != 2:
            continue
        lat = _parse_coord(parts[0])
        lon = _parse_coord(parts[1])
        points.append((lat, lon))

    _POLYGON = points

    if points:
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        _BBOX = (min(lats), max(lats), min(lons), max(lons))

    return _POLYGON


def point_in_polygon(lat: float, lon: float) -> bool:
    """Ray-casting algorithm to check if a point is inside the airspace polygon."""
    polygon = _load_polygon()
    if not polygon:
        return False

    if _BBOX:
        min_lat, max_lat, min_lon, max_lon = _BBOX
        if lat < min_lat or lat > max_lat or lon < min_lon or lon > max_lon:
            return False

    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if ((lon_i > lon) != (lon_j > lon)) and \
           (lat < (lat_j - lat_i) * (lon - lon_i) / (lon_j - lon_i) + lat_i):
            inside = not inside
        j = i
    return inside


# --- Projection ---
# Use equirectangular projection with cos(lat) correction so that
# one degree of longitude is properly scaled relative to latitude.
# This gives a correct WGS84 appearance.

import math

_PROJ_CACHE: dict | None = None


def _get_proj_params():
    """Compute projection parameters from the polygon bounding box."""
    global _PROJ_CACHE
    if _PROJ_CACHE is not None:
        return _PROJ_CACHE

    _load_polygon()
    if not _BBOX:
        # Fallback
        _PROJ_CACHE = {
            "min_lat": 48.0, "max_lat": 57.5,
            "min_lon": -15.5, "max_lon": -5.0,
            "cos_lat": math.cos(math.radians(52.75)),
        }
        return _PROJ_CACHE

    min_lat, max_lat, min_lon, max_lon = _BBOX
    center_lat = (min_lat + max_lat) / 2.0
    cos_lat = math.cos(math.radians(center_lat))

    # Convert to projected coordinates to find proper bounds
    # Projected x = lon * cos(center_lat), y = lat
    proj_points = []
    for lat, lon in _POLYGON:
        px = lon * cos_lat
        py = lat
        proj_points.append((px, py))

    pxs = [p[0] for p in proj_points]
    pys = [p[1] for p in proj_points]

    # Add 18% padding so the FIR fits inside the radar rings
    px_span = max(pxs) - min(pxs)
    py_span = max(pys) - min(pys)
    pad_x = px_span * 0.18
    pad_y = py_span * 0.18

    _PROJ_CACHE = {
        "min_px": min(pxs) - pad_x,
        "max_px": max(pxs) + pad_x,
        "min_py": min(pys) - pad_y,
        "max_py": max(pys) + pad_y,
        "cos_lat": cos_lat,
    }
    return _PROJ_CACHE


def _project(lat: float, lon: float) -> tuple[float, float]:
    """Project lat/lon to normalised 0-1 coordinates using equirectangular with cos(lat) correction."""
    p = _get_proj_params()
    cos_lat = p["cos_lat"]

    # Project
    px = lon * cos_lat
    py = lat

    # Normalise to 0-1
    x = (px - p["min_px"]) / (p["max_px"] - p["min_px"])
    y = 1.0 - (py - p["min_py"]) / (p["max_py"] - p["min_py"])
    return x, y


def lat_lon_to_radar(lat: float, lon: float) -> tuple[float, float]:
    """Convert lat/lon to radar percentage coordinates (0-100)."""
    x, y = _project(lat, lon)
    x = max(0.02, min(0.98, x))
    y = max(0.02, min(0.98, y))
    return (round(x * 100, 1), round(y * 100, 1))


def get_sector_svg_points(size: int = 280) -> str:
    """Convert the airspace polygon to SVG polygon points string scaled to radar size."""
    polygon = _load_polygon()
    if not polygon:
        return ""

    points = []
    for lat, lon in polygon:
        x, y = _project(lat, lon)
        points.append(f"{x * size:.1f},{y * size:.1f}")

    return " ".join(points)


def get_airport_radar_positions() -> list[dict]:
    """Get reference airport positions projected onto the radar."""
    result = []
    for apt in REFERENCE_AIRPORTS:
        x, y = lat_lon_to_radar(apt["lat"], apt["lon"])
        result.append({
            "icao": apt["icao"],
            "name": apt["name"],
            "x": x,
            "y": y,
        })
    return result


def format_altitude(alt_feet: int) -> str:
    """Format altitude: FL350 for >5000ft, A32 for <=5000ft."""
    if alt_feet > 5000:
        fl = round(alt_feet / 100)
        return f"FL{fl}"
    else:
        a = round(alt_feet / 100)
        return f"A{a:02d}" if a < 10 else f"A{a}"
