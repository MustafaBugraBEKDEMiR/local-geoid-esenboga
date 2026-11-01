"""Monte-Carlo comparison of local geoid methods.

A GNSS/levelling survey is simulated: control points are placed in the study
area, their "observed" geoid height is the reference geoid (TG-20) plus
random measurement noise (GNSS ellipsoidal height + levelling, sigma ~2 cm).
Each method is fitted to the control points and evaluated against the
reference geoid on a dense set of independent check points.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

from .data import StudyData
from .models import (GlobalModelOnly, KrigingSurface, PolynomialSurface, RBFSurface,
                     RemoveRestore)


def sample_in_polygon(poly: Polygon, n: int, rng: np.random.Generator,
                      min_dist: float = 0.0, max_tries: int = 20000) -> np.ndarray:
    """Random points inside ``poly`` with an optional minimum spacing (m)."""
    p = prep(poly)
    minx, miny, maxx, maxy = poly.bounds
    pts: list[tuple[float, float]] = []
    tries = 0
    while len(pts) < n and tries < max_tries:
        tries += 1
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if not p.contains(Point(x, y)):
            continue
        if min_dist and pts and np.min(np.hypot(*(np.array(pts) - (x, y)).T)) < min_dist:
            continue
        pts.append((x, y))
    if len(pts) < n:
        raise RuntimeError("could not place points; lower min_dist")
    return np.array(pts)


def grid_in_polygon(poly: Polygon, spacing: float) -> np.ndarray:
    p = prep(poly)
    minx, miny, maxx, maxy = poly.bounds
    xs, ys = np.meshgrid(np.arange(minx, maxx, spacing), np.arange(miny, maxy, spacing))
    pts = np.c_[xs.ravel(), ys.ravel()]
    return pts[[p.contains(Point(*q)) for q in pts]]


def default_methods(data: StudyData) -> list:
    g = data.n_egm
    return [
        GlobalModelOnly(g),
        PolynomialSurface(1),
        PolynomialSurface(2),
        RBFSurface(smoothing=1e-3),
        KrigingSurface(),
        RemoveRestore(g, PolynomialSurface(0), name="EGM2008 + constant shift"),
        RemoveRestore(g, PolynomialSurface(1)),
        RemoveRestore(g, KrigingSurface()),
    ]


@dataclass
class Scenario:
    name: str
    area: Polygon
    n_points: int
    noise_m: float = 0.02
    min_dist: float = 0.0


def run_scenario(data: StudyData, sc: Scenario, reps: int = 200, seed: int = 42,
                 check_spacing: float | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    if check_spacing is None:
        check_spacing = np.sqrt(sc.area.area / 1500)
    chk = grid_in_polygon(sc.area, check_spacing)
    n_chk_true = data.n_true(chk[:, 0], chk[:, 1])
    rows = []
    for r in range(reps):
        cp = sample_in_polygon(sc.area, sc.n_points, rng, sc.min_dist)
        n_obs = data.n_true(cp[:, 0], cp[:, 1]) + rng.normal(0, sc.noise_m, len(cp))
        for proto in default_methods(data):
            m = copy.deepcopy(proto)
            try:
                m.fit(cp[:, 0], cp[:, 1], n_obs)
                err = m.predict(chk[:, 0], chk[:, 1]) - n_chk_true
            except (ValueError, np.linalg.LinAlgError):
                continue
            rows.append(dict(scenario=sc.name, n_points=sc.n_points, noise_m=sc.noise_m,
                             rep=r, method=m.name,
                             rmse=float(np.sqrt(np.mean(err**2))),
                             bias=float(np.mean(err)),
                             max_abs=float(np.max(np.abs(err)))))
    return pd.DataFrame(rows)


def region_box(center_xy: tuple[float, float], width: float, height: float) -> Polygon:
    cx, cy = center_xy
    return box(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
