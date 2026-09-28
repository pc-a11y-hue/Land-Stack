"""
Pure-Python geometry for parcel boundaries (no GIS library required).

Coordinates: WGS-84 (EPSG:4326). Public input is [lat, lon] pairs (what the
map UI produces); stored geometry is GeoJSON (RFC 7946) [lon, lat].

Areas and distances are computed in a local equirectangular projection
centred on the polygon — accurate to well under 0.1% at parcel scale. That
is fine for cadastral-sized plots; a production system should use the
official projected CRS for each state (UTM zone / state plane) and a
topology-aware library such as PostGIS.
"""
import math

EARTH_R = 6371008.8
M_PER_DEG_LAT = math.pi * EARTH_R / 180.0


# ---------------------------------------------------------------- conversion
def latlon_to_ring(points):
    """[[lat, lon], ...] -> closed GeoJSON ring [[lon, lat], ...]."""
    ring = [[float(p[1]), float(p[0])] for p in points]
    if ring and ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    return ring


def _open(ring):
    return ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else list(ring)


def _project(ring, lat0=None, lon0=None):
    pts = _open(ring)
    if lat0 is None:
        lat0 = sum(p[1] for p in pts) / len(pts)
        lon0 = sum(p[0] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))
    return [((p[0] - lon0) * M_PER_DEG_LAT * k, (p[1] - lat0) * M_PER_DEG_LAT) for p in pts], lat0, lon0


def _shoelace(xy):
    s = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def polygon_area_sqm(ring):
    xy, _, _ = _project(ring)
    return abs(_shoelace(xy))


def polygon_centroid(ring):
    """Area-weighted centroid; returns (lat, lon)."""
    xy, lat0, lon0 = _project(ring)
    a = _shoelace(xy)
    if abs(a) < 1e-9:
        return lat0, lon0
    cx = cy = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    cx /= 6 * a
    cy /= 6 * a
    k = math.cos(math.radians(lat0))
    return lat0 + cy / M_PER_DEG_LAT, lon0 + cx / (M_PER_DEG_LAT * k)


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a)) / 1000.0


def bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------- primitives
def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4):
    """Proper crossing (interiors intersect at a single point)."""
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def _point_seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _inside(pt, xy):
    """Ray-casting point-in-polygon on projected coordinates."""
    x, y = pt
    inside = False
    n = len(xy)
    for i in range(n):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _depth_inside(pt, xy):
    """Distance from pt to the boundary if inside, else 0."""
    if not _inside(pt, xy):
        return 0.0
    n = len(xy)
    return min(_point_seg_dist(pt, xy[i], xy[(i + 1) % n]) for i in range(n))


# ------------------------------------------------------------- validation
def is_simple(ring):
    """True if no two non-adjacent edges cross."""
    xy, _, _ = _project(ring)
    n = len(xy)
    for i in range(n):
        a1, a2 = xy[i], xy[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            if _segments_cross(a1, a2, xy[j], xy[(j + 1) % n]):
                return False
    return True


def validate_boundary(points, min_sqm, max_sqm):
    """
    points: [[lat, lon], ...] from the map UI.
    Returns (ring, area_sqm, errors). ring is None if invalid.
    """
    errors = []
    try:
        pts = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        return None, 0.0, ["Boundary must be a list of [latitude, longitude] pairs."]
    for lat, lon in pts:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None, 0.0, ["A boundary point has an out-of-range latitude/longitude."]
    unique = {(round(a, 7), round(b, 7)) for a, b in pts}
    if len(unique) < 3:
        return None, 0.0, ["A plot boundary needs at least 3 distinct points."]
    ring = latlon_to_ring(pts)
    if not is_simple(ring):
        return None, 0.0, ["The boundary crosses itself — redraw it so the outline doesn't intersect."]
    area = polygon_area_sqm(ring)
    if area < min_sqm:
        errors.append(f"Boundary area {area:.1f} sq.m is below the minimum of {min_sqm} sq.m.")
    if area > max_sqm:
        errors.append(f"Boundary area {area:,.0f} sq.m exceeds the maximum of {max_sqm:,} sq.m.")
    return (ring if not errors else None), area, errors


def within_radius(ring, center, radius_km):
    """All vertices within radius_km of center (lat, lon) — stand-in for a district polygon test."""
    return all(haversine_km(center[0], center[1], p[1], p[0]) <= radius_km for p in _open(ring))


# ---------------------------------------------------------------- overlap
def overlap_info(ring_a, ring_b, tol_m=0.5, min_fraction=0.005, grid=80):
    """
    Decide whether two polygons overlap by more than a sliver.
    Returns {"overlaps": bool, "fraction": share of the SMALLER polygon that
    lies inside the other (sampled), "depth_m": deepest vertex penetration}.

    Touching edges / tiny GPS-level slivers (< tol_m deep and < min_fraction
    of area) are NOT counted as overlap, so neighbouring plots that share a
    boundary register fine.
    """
    ax0, ay0, ax1, ay1 = bbox(ring_a)
    bx0, by0, bx1, by1 = bbox(ring_b)
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return {"overlaps": False, "fraction": 0.0, "depth_m": 0.0}

    lat0 = (ay0 + ay1 + by0 + by1) / 4
    lon0 = (ax0 + ax1 + bx0 + bx1) / 4
    A, _, _ = _project(ring_a, lat0, lon0)
    B, _, _ = _project(ring_b, lat0, lon0)

    depth = max([_depth_inside(p, B) for p in A] + [_depth_inside(p, A) for p in B])

    small, large = (A, B) if abs(_shoelace(A)) <= abs(_shoelace(B)) else (B, A)
    xs = [p[0] for p in small]
    ys = [p[1] for p in small]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    hits = total = 0
    for i in range(grid):
        for j in range(grid):
            pt = (x0 + (i + 0.5) * (x1 - x0) / grid, y0 + (j + 0.5) * (y1 - y0) / grid)
            if _inside(pt, small):
                total += 1
                if _inside(pt, large):
                    hits += 1
    fraction = hits / total if total else 0.0
    return {"overlaps": bool(fraction >= min_fraction or depth >= tol_m),
            "fraction": round(fraction, 4), "depth_m": round(depth, 2)}


# ------------------------------------------------------------ seed helper
def square_around(lat, lon, area_sqm, angle_deg=0.0):
    """A square of exactly area_sqm centred on (lat, lon), rotated by angle_deg. Returns a GeoJSON ring."""
    half = math.sqrt(area_sqm) / 2.0
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    k = math.cos(math.radians(lat))
    ring = []
    for dx, dy in [(-half, -half), (half, -half), (half, half), (-half, half)]:
        rx, ry = dx * ca - dy * sa, dx * sa + dy * ca
        ring.append([lon + rx / (M_PER_DEG_LAT * k), lat + ry / M_PER_DEG_LAT])
    ring.append(list(ring[0]))
    return ring


def offset_point(lat, lon, north_m, east_m):
    k = math.cos(math.radians(lat))
    return lat + north_m / M_PER_DEG_LAT, lon + east_m / (M_PER_DEG_LAT * k)
