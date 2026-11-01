"""Loading the open datasets used in the study.

All inputs live in ``data/raw`` and come from open sources:

* TG-20 Turkish hybrid geoid (Yıldız et al. 2020, CC BY 4.0) — used as the
  reference ("true") geoid because it is the official national model and is
  fitted to the national height datum TUDKA-99.
* EGM2008 2.5' grid (NGA, via the PROJ-data repository) — the global model
  most GNSS receivers and GIS packages use by default.
* OpenStreetMap campus boundary (ODbL).
* SRTM 1" terrain heights (public domain) for the engineering examples.

Planar coordinates are TUREF / TM33 (EPSG:5255), the official Turkish
3-degree Transverse Mercator zone covering Ankara.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator
import shapely
from shapely.geometry import Polygon, shape

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PLANAR_EPSG = 5255  # TUREF / TM33

_to_tm = Transformer.from_crs(4326, PLANAR_EPSG, always_xy=True)
_to_geo = Transformer.from_crs(PLANAR_EPSG, 4326, always_xy=True)


def lonlat_to_tm(lon, lat):
    """Geographic (deg) -> TUREF/TM33 easting, northing (m)."""
    return _to_tm.transform(lon, lat)


def tm_to_lonlat(x, y):
    return _to_geo.transform(x, y)


def _tg20_interpolator(path: Path) -> RegularGridInterpolator:
    df = pd.read_csv(path, comment="#")
    lats = np.sort(df.lat.unique())
    lons = np.sort(df.lon.unique())
    grid = df.pivot(index="lat", columns="lon", values="N_tg20").loc[lats, lons].values
    return RegularGridInterpolator((lats, lons), grid, method="cubic")


def _egm2008_interpolator(path: Path) -> RegularGridInterpolator:
    with rasterio.open(path) as src:
        a = src.read(1).astype(float)
        t = src.transform
    # AREA_OR_POINT=Area: node values sit at pixel centres
    lats = t.f + t.e * (np.arange(a.shape[0]) + 0.5)
    lons = t.c + t.a * (np.arange(a.shape[1]) + 0.5)
    return RegularGridInterpolator((lats[::-1], lons), a[::-1], method="cubic")


@dataclass
class StudyData:
    tg20: RegularGridInterpolator
    egm2008: RegularGridInterpolator
    campus_ll: Polygon  # lon/lat
    campus_tm: Polygon  # TUREF/TM33 metres
    srtm: pd.DataFrame

    # ---- geoid look-ups in planar coordinates --------------------------
    def n_true(self, x, y):
        """Reference geoid height (TG-20) at TM33 coordinates."""
        lon, lat = tm_to_lonlat(np.asarray(x), np.asarray(y))
        return self.tg20(np.c_[np.ravel(lat), np.ravel(lon)]).reshape(np.shape(x))

    def n_egm(self, x, y):
        """EGM2008 geoid height at TM33 coordinates."""
        lon, lat = tm_to_lonlat(np.asarray(x), np.asarray(y))
        return self.egm2008(np.c_[np.ravel(lat), np.ravel(lon)]).reshape(np.shape(x))


def load_study_data(raw: Path = RAW) -> StudyData:
    gj = json.loads((raw / "aybu_esenboga_campus_osm.geojson").read_text(encoding="utf-8"))
    campus_ll = shape(gj["features"][0]["geometry"])
    campus_tm = shapely.transform(campus_ll, lambda c: np.column_stack(lonlat_to_tm(c[:, 0], c[:, 1])))
    srtm = pd.read_csv(raw / "srtm30m_campus_grid.csv", comment="#")
    srtm["x"], srtm["y"] = lonlat_to_tm(srtm.lon.values, srtm.lat.values)
    return StudyData(
        tg20=_tg20_interpolator(raw / "tg20_ankara_window.csv"),
        egm2008=_egm2008_interpolator(raw / "egm2008_2p5min_ankara.tif"),
        campus_ll=campus_ll,
        campus_tm=campus_tm,
        srtm=srtm,
    )
