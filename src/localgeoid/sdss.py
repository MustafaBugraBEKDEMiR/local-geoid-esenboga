"""A small spatial decision support (SDSS) scenario on the campus.

Question: *where could a new building go?* Every 10 m cell inside the campus
is screened with the same rules twice:

* once with heights from GNSS + TG-20 (the reference), and
* once with heights from GNSS + EGM2008 (a common shortcut).

Both runs share every input except the geoid, so any difference in the result
is caused by the vertical datum alone.

Rules (all thresholds are HYPOTHETICAL scenario parameters, not real
municipal or aviation values):

1. Site constraints (identical in both runs)
   - terrain slope <= ``max_slope``
   - at least ``building_buffer`` m from existing buildings
   - not on pitches or parking
   - within ``max_road_dist`` m of a road
2. Rule A, gravity sewer connection to a manhole whose invert level is given
   in the national datum: ``H - cover - fall * L >= invert``,
   with L the straight-line distance to the manhole.
   Lower heights make this rule fail -> EGM2008 *loses* valid sites.
3. Rule B, absolute height limit (e.g. an obstacle-limitation surface given
   as an elevation): ``H + building_height <= height_cap``.
   Lower heights make this rule pass -> EGM2008 *approves* sites that break
   the limit.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import LineString, Point, Polygon
from shapely.prepared import prep

from .data import StudyData, lonlat_to_tm, tm_to_lonlat


@dataclass
class Scenario:
    cell: float = 10.0
    max_slope: float = 0.08            # 8 %
    building_buffer: float = 15.0      # m
    max_road_dist: float = 200.0       # m
    # rule A: gravity sewer
    manhole_lonlat: tuple = (32.95653, 40.12570)  # SE roundabout (OSM)
    invert_depth: float = 2.5          # manhole invert below ground at the manhole (m)
    cover: float = 1.5                 # pipe cover at the building (m)
    fall: float = 0.005                # pipe fall (m/m)
    # rule B: absolute height cap
    building_height: float = 20.0      # m
    height_cap: float = 975.0          # m, national datum


def _dem_sampler(data: StudyData):
    dem = data.srtm
    lats = np.sort(dem.lat.unique())
    lons = np.sort(dem.lon.unique())
    G = dem.pivot(index="lat", columns="lon", values="H_srtm").loc[lats, lons].values
    f = RegularGridInterpolator((lats, lons), G, bounds_error=False, fill_value=None)

    def H(x, y):
        lon, lat = tm_to_lonlat(np.asarray(x), np.asarray(y))
        return f(np.c_[np.ravel(lat), np.ravel(lon)]).reshape(np.shape(x))
    return H


def evaluate(data: StudyData, osm_elements: list, sc: Scenario = Scenario()) -> dict:
    """Run the screening on a regular grid; returns arrays on that grid."""
    H_at = _dem_sampler(data)
    campus = data.campus_tm
    minx, miny, maxx, maxy = campus.bounds
    xs = np.arange(minx, maxx, sc.cell) + sc.cell / 2
    ys = np.arange(miny, maxy, sc.cell) + sc.cell / 2
    X, Y = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(campus, X, Y)

    H = H_at(X, Y)                                  # reference orthometric height
    dHy, dHx = np.gradient(H, sc.cell)
    slope = np.hypot(dHx, dHy)
    offset = data.n_true(X, Y) - data.n_egm(X, Y)   # H_egm - H_true (≈ -0.34 m)
    H_egm = H + offset

    blds, areas, roads = [], [], []
    for el in osm_elements:
        t, g = el["tags"], np.asarray(el["g"])
        if len(g) < 2:
            continue
        x, y = lonlat_to_tm(g[:, 0], g[:, 1])
        if "building" in t:
            blds.append(Polygon(np.c_[x, y]).buffer(0))
        elif "leisure" in t or t.get("amenity") == "parking":
            areas.append(Polygon(np.c_[x, y]).buffer(0))
        elif "highway" in t:
            roads.append(LineString(np.c_[x, y]))
    excl = shapely.union_all([b.buffer(sc.building_buffer) for b in blds] + areas)
    road_zone = shapely.union_all([r.buffer(sc.max_road_dist) for r in roads])
    site_ok = (inside & (slope <= sc.max_slope)
               & ~shapely.contains_xy(excl, X, Y) & shapely.contains_xy(road_zone, X, Y))

    mx, my = lonlat_to_tm(*sc.manhole_lonlat)
    H_mh = float(H_at(mx, my))
    invert = H_mh - sc.invert_depth
    L = np.hypot(X - mx, Y - my)

    def rule_a(h):
        return h - sc.cover - sc.fall * L >= invert

    def rule_b(h):
        return h + sc.building_height <= sc.height_cap

    out = dict(X=X, Y=Y, inside=inside, H=H, H_egm=H_egm, slope=slope, site_ok=site_ok,
               manhole=(mx, my, H_mh, invert), scenario=sc)
    for name, rule in (("A", rule_a), ("B", rule_b)):
        ok_ref, ok_egm = site_ok & rule(H), site_ok & rule(H_egm)
        out[name] = dict(ref=ok_ref, egm=ok_egm,
                         lost=ok_ref & ~ok_egm,        # valid site rejected by EGM2008
                         wrongly_ok=~ok_ref & ok_egm)  # invalid site accepted by EGM2008
    return out


def summary(res: dict) -> dict:
    a = res["scenario"].cell ** 2 / 1e4  # ha per cell
    s = {"eligible_ha": res["site_ok"].sum() * a}
    for k in ("A", "B"):
        r = res[k]
        s[k] = {m: round(float(r[m].sum() * a), 2) for m in ("ref", "egm", "lost", "wrongly_ok")}
    return s


def sweep(res: dict, rule: str, offsets: np.ndarray) -> np.ndarray:
    """Share (%) of eligible area whose decision flips, for shifted thresholds."""
    sc, H, H_egm, ok = res["scenario"], res["H"], res["H_egm"], res["site_ok"]
    mx, my, H_mh, invert = res["manhole"]
    L = np.hypot(res["X"] - mx, res["Y"] - my)
    out = []
    for d in offsets:
        if rule == "A":
            f = lambda h: h - sc.cover - sc.fall * L >= invert + d  # noqa: E731
        else:
            f = lambda h: h + sc.building_height <= sc.height_cap + d  # noqa: E731
        flip = ok & (f(H) != f(H_egm))
        out.append(100 * flip.sum() / max(ok.sum(), 1))
    return np.array(out)
