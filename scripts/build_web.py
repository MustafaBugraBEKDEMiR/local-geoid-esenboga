"""Build the 3D campus viewer (web/index.html) from the raw data.

The scene is expressed in a local frame centred on the campus centroid:
E (east, m), N (north, m) in TUREF/TM33 and orthometric height H (m).
All geometry is pre-triangulated here so the page only has to upload buffers.

Usage:  python scripts/build_web.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from scipy.interpolate import RegularGridInterpolator  # noqa: E402
from scipy.spatial import Delaunay  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.prepared import prep  # noqa: E402

from localgeoid import load_study_data  # noqa: E402
from localgeoid.data import lonlat_to_tm, tm_to_lonlat  # noqa: E402

RAW = ROOT / "data" / "raw"
WEB = ROOT / "web"

d = load_study_data()
campus = d.campus_tm
c = campus.centroid
X0, Y0 = round(c.x, 1), round(c.y, 1)

# ---------------------------------------------------------------- DEM sampler
dem = pd.read_csv(RAW / "srtm30m_campus_grid.csv", comment="#")
lats = np.sort(dem.lat.unique())
lons = np.sort(dem.lon.unique())
Hgrid = dem.pivot(index="lat", columns="lon", values="H_srtm").loc[lats, lons].values
_dem = RegularGridInterpolator((lats, lons), Hgrid, method="linear", bounds_error=False,
                               fill_value=None)


def H_at(x, y):
    lon, lat = tm_to_lonlat(np.asarray(x), np.asarray(y))
    return _dem(np.c_[np.ravel(lat), np.ravel(lon)])


def r(a, nd=2):
    return [round(float(v), nd) for v in np.ravel(a)]


# ---------------------------------------------------------------- terrain mesh
ring = LineString(campus.exterior.coords)
step_b = 8.0
bpts = np.array([ring.interpolate(t).coords[0] for t in np.arange(0, ring.length, step_b)])
minx, miny, maxx, maxy = campus.bounds
sp = 18.0
gx, gy = np.meshgrid(np.arange(minx, maxx, sp), np.arange(miny, maxy, sp))
gp = np.c_[gx.ravel(), gy.ravel()]
inner = prep(campus.buffer(-sp * 0.45))
gp = gp[[inner.contains(Point(*p)) for p in gp]]
V = np.vstack([bpts, gp])
tri = Delaunay(V).simplices
pc = prep(campus)
cent = V[tri].mean(axis=1)
tri = tri[[pc.contains(Point(*p)) for p in cent]]
# orient every triangle counter-clockwise in (E, N) so it faces up (+H)
a, b, cc = V[tri[:, 0]], V[tri[:, 1]], V[tri[:, 2]]
cw = ((b[:, 0] - a[:, 0]) * (cc[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (cc[:, 0] - a[:, 0])) < 0
tri[cw] = tri[cw][:, [0, 2, 1]]
Hv = H_at(V[:, 0], V[:, 1])
Ntg = d.n_true(V[:, 0], V[:, 1])
Neg = d.n_egm(V[:, 0], V[:, 1])
nb = len(bpts)  # first nb vertices are the boundary ring (in order)
base = float(np.floor(Hv.min() - 6))

terrain = dict(E=r(V[:, 0] - X0, 1), N=r(V[:, 1] - Y0, 1), H=r(Hv, 2),
               Ntg=r(Ntg, 4), Neg=r(Neg, 4), tri=tri.astype(int).ravel().tolist(),
               nBoundary=nb, base=base)

# ---------------------------------------------------------------- OSM features
osm = json.loads((RAW / "osm_campus_features.json").read_text(encoding="utf-8"))["elements"]
HEIGHT = {"college": 18.0, "university": 12.0, "dormitory": 21.0, "yes": 7.0}
TYPE_TR = {"college": "Fakülte / eğitim binası", "university": "Üniversite binası",
           "dormitory": "Öğrenci yurdu", "yes": "Bina"}
ROAD_W = {"tertiary": 9.0, "unclassified": 7.5, "residential": 6.0, "service": 4.0}

buildings, roads, areas, pois = [], [], [], []
clip = campus.buffer(3.0)
for el in osm:
    t, g = el["tags"], np.array(el["g"])
    x, y = lonlat_to_tm(g[:, 0], g[:, 1])
    if "building" in t:
        poly = Polygon(np.c_[x, y]).buffer(0)
        if poly.area < 20:
            continue
        ext = np.array(poly.exterior.coords)[:-1]
        if Polygon(ext).exterior.is_ccw is False:
            ext = ext[::-1]
        hb = H_at(ext[:, 0], ext[:, 1])
        btype = t["building"]
        buildings.append(dict(
            id=el["id"], name=t.get("name", ""), type=TYPE_TR.get(btype, btype),
            h=HEIGHT.get(btype, 7.0), z=round(float(hb.min()) - 0.5, 2),
            E=r(ext[:, 0] - X0, 1), N=r(ext[:, 1] - Y0, 1),
            area=round(poly.area)))
    elif "highway" in t and len(g) > 1:
        line = LineString(np.c_[x, y]).intersection(clip)
        if line.is_empty:
            continue
        parts = [line] if line.geom_type == "LineString" else list(getattr(line, "geoms", []))
        w = ROAD_W.get(t["highway"], 5.0)
        for p in parts:
            if p.geom_type != "LineString" or p.length < 5:
                continue
            p = p.segmentize(6.0)
            P = np.array(p.coords)
            dvec = np.gradient(P, axis=0)
            nrm = np.c_[-dvec[:, 1], dvec[:, 0]]
            nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
            L, R = P + nrm * w / 2, P - nrm * w / 2
            hl, hr = H_at(L[:, 0], L[:, 1]), H_at(R[:, 0], R[:, 1])
            roads.append(dict(cls=t["highway"], name=t.get("name", ""),
                              L=r(np.c_[L[:, 0] - X0, L[:, 1] - Y0, hl + 0.35], 1),
                              R=r(np.c_[R[:, 0] - X0, R[:, 1] - Y0, hr + 0.35], 1)))
    elif ("leisure" in t or t.get("amenity") == "parking" or t.get("landuse") == "grass") \
            and len(g) > 3:
        poly = Polygon(np.c_[x, y]).buffer(0).intersection(campus)
        if poly.is_empty:
            continue
        poly = shapely.segmentize(poly, 12.0)
        tris = shapely.constrained_delaunay_triangles(poly)
        pts = []
        for tr in tris.geoms:
            q = np.array(tr.exterior.coords)[:3]
            hq = H_at(q[:, 0], q[:, 1]) + 0.2
            pts += r(np.c_[q[:, 0] - X0, q[:, 1] - Y0, hq], 1)
        kind = "pitch" if "leisure" in t else ("parking" if t.get("amenity") == "parking" else "grass")
        areas.append(dict(kind=kind, tris=pts))
    elif el["id"].startswith("n") and t.get("name"):
        pois.append(dict(name=t["name"] + (" (planlanan metro istasyonu)" if t.get("railway") == "proposed" else ""),
                         E=round(x[0] - X0, 1), N=round(y[0] - Y0, 1),
                         H=round(float(H_at(x, y)[0]), 1)))

# ---------------------------------------------------------------- control points
lay = pd.read_csv(ROOT / "data/processed/recommended_layouts.csv")
lay = lay[(lay.scenario == "campus") & (lay.n_points == 8)]
cps = {}
for st, g in lay.groupby("strategy"):
    cps[st] = [dict(id=row.id, E=round(row.x - X0, 1), N=round(row.y - Y0, 1),
                    H=round(float(H_at(row.x, row.y)[0]), 2),
                    Ntg=round(float(d.n_true(row.x, row.y)), 3),
                    Neg=round(float(d.n_egm(row.x, row.y)), 3)) for row in g.itertuples()]

# ---------------------------------------------------------------- local -> lon/lat (affine fit)
smp = np.c_[np.random.default_rng(0).uniform(minx, maxx, 400), np.random.default_rng(1).uniform(miny, maxy, 400)]
lo, la = tm_to_lonlat(smp[:, 0], smp[:, 1])
A = np.c_[np.ones(len(smp)), smp[:, 0] - X0, smp[:, 1] - Y0]
cl, *_ = np.linalg.lstsq(A, lo, rcond=None)
ca, *_ = np.linalg.lstsq(A, la, rcond=None)
geo_err = max(np.abs(A @ cl - lo).max(), np.abs(A @ ca - la).max()) * 111_000

scene = dict(
    origin=dict(E=X0, N=Y0, epsg=5255),
    lonlat=dict(lon=r(cl, 10), lat=r(ca, 10)),
    stats=dict(area_km2=round(campus.area / 1e6, 2),
               Ntg_min=round(float(Ntg.min()), 3), Ntg_max=round(float(Ntg.max()), 3),
               Neg_mean=round(float(Neg.mean()), 3), Ntg_mean=round(float(Ntg.mean()), 3),
               H_min=round(float(Hv.min()), 1), H_max=round(float(Hv.max()), 1)),
    terrain=terrain, boundary=dict(E=r(bpts[:, 0] - X0, 1), N=r(bpts[:, 1] - Y0, 1)),
    buildings=buildings, roads=roads, areas=areas, pois=pois, controlPoints=cps,
)
tpl = (WEB / "template.html").read_text(encoding="utf-8")
html = tpl.replace("/*__SCENE__*/null", json.dumps(scene, ensure_ascii=False, separators=(",", ":")))
(WEB / "index.html").write_text(html, encoding="utf-8")
print(f"vertices {len(V)}  triangles {len(tri)}  buildings {len(buildings)}  roads {len(roads)}  "
      f"areas {len(areas)}  html {len(html)/1e6:.2f} MB  lon/lat fit err {geo_err:.2f} m")
