"""WGS84 latitude/longitude to the British National Grid (spot spec section 10).

The Ordnance Survey 7-parameter Helmert transform to OSGB36 and the National Grid
transverse Mercator projection, as pure functions. Moved here from
scripts/haduk_normals.py so the app's 1 km lookups and the scripts share one transform.
The Helmert step is good to a few metres, so a point within a few metres of a cell edge
may land in the neighbouring cell; lookups use the rounded location (about 1 km) anyway.
"""

from __future__ import annotations

import math

CELL_M = 1000  # the 1 km grid every spot lookup uses

# Ellipsoids (semi-major, semi-minor axes in metres).
WGS84 = (6378137.000, 6356752.3141)
AIRY1830 = (6377563.396, 6356256.909)
# OS Helmert WGS84 -> OSGB36: translations (m), scale (ppm), rotations (arc-seconds).
HELMERT = {
    "tx": -446.448,
    "ty": 125.157,
    "tz": -542.060,
    "s": 20.4894,
    "rx": -0.1502,
    "ry": -0.2470,
    "rz": -0.8421,
}
# National Grid transverse Mercator.
F0 = 0.9996012717
LAT0, LON0 = math.radians(49), math.radians(-2)
E0, N0 = 400000.0, -100000.0


def _to_cartesian(
    lat: float, lon: float, ellipsoid: tuple[float, float]
) -> tuple[float, float, float]:
    a, b = ellipsoid
    e2 = 1 - (b * b) / (a * a)
    phi, lam = math.radians(lat), math.radians(lon)
    nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return (
        nu * math.cos(phi) * math.cos(lam),
        nu * math.cos(phi) * math.sin(lam),
        (1 - e2) * nu * math.sin(phi),
    )


def _to_geodetic(
    x: float, y: float, z: float, ellipsoid: tuple[float, float]
) -> tuple[float, float]:
    a, b = ellipsoid
    e2 = 1 - (b * b) / (a * a)
    p = math.hypot(x, y)
    phi = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(z + e2 * nu * math.sin(phi), p)
    return math.degrees(phi), math.degrees(math.atan2(y, x))


def wgs84_to_osgb36(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 latitude/longitude (degrees) to OSGB36 latitude/longitude (degrees)."""
    x, y, z = _to_cartesian(lat, lon, WGS84)
    s = HELMERT["s"] * 1e-6
    rx, ry, rz = (math.radians(HELMERT[k] / 3600) for k in ("rx", "ry", "rz"))
    x2 = HELMERT["tx"] + (1 + s) * x - rz * y + ry * z
    y2 = HELMERT["ty"] + rz * x + (1 + s) * y - rx * z
    z2 = HELMERT["tz"] - ry * x + rx * y + (1 + s) * z
    return _to_geodetic(x2, y2, z2, AIRY1830)


def osgb36_to_bng(lat: float, lon: float) -> tuple[float, float]:
    """OSGB36 latitude/longitude (degrees) to National Grid easting/northing (metres)."""
    a, b = AIRY1830
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)
    phi, lam = math.radians(lat), math.radians(lon)
    sin, cos, tan = math.sin(phi), math.cos(phi), math.tan(phi)
    nu = a * F0 / math.sqrt(1 - e2 * sin * sin)
    rho = a * F0 * (1 - e2) / (1 - e2 * sin * sin) ** 1.5
    eta2 = nu / rho - 1
    dp, sp = phi - LAT0, phi + LAT0
    m = (
        b
        * F0
        * (
            (1 + n + 5 / 4 * n**2 + 5 / 4 * n**3) * dp
            - (3 * n + 3 * n**2 + 21 / 8 * n**3) * math.sin(dp) * math.cos(sp)
            + (15 / 8 * n**2 + 15 / 8 * n**3) * math.sin(2 * dp) * math.cos(2 * sp)
            - 35 / 24 * n**3 * math.sin(3 * dp) * math.cos(3 * sp)
        )
    )
    i = m + N0
    ii = nu / 2 * sin * cos
    iii = nu / 24 * sin * cos**3 * (5 - tan**2 + 9 * eta2)
    iiia = nu / 720 * sin * cos**5 * (61 - 58 * tan**2 + tan**4)
    iv = nu * cos
    v = nu / 6 * cos**3 * (nu / rho - tan**2)
    vi = nu / 120 * cos**5 * (5 - 18 * tan**2 + tan**4 + 14 * eta2 - 58 * tan**2 * eta2)
    dl = lam - LON0
    north = i + ii * dl**2 + iii * dl**4 + iiia * dl**6
    east = E0 + iv * dl + v * dl**3 + vi * dl**5
    return east, north


def latlon_to_bng(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 latitude/longitude (degrees) to British National Grid easting/northing (m)."""
    return osgb36_to_bng(*wgs84_to_osgb36(lat, lon))


def cell_of(lat: float, lon: float) -> tuple[int, int]:
    """The 1 km cell (easting km, northing km) holding a WGS84 point: the cell's south-west
    corner in kilometres."""
    east, north = latlon_to_bng(lat, lon)
    return math.floor(east / CELL_M), math.floor(north / CELL_M)
