"""Where should the GNSS/levelling control points go?

Three placement strategies are compared for a fixed budget of *n* points:

* ``random``      – points dropped uniformly at random (the baseline used in
                    :mod:`localgeoid.experiment`).
* ``maximin``     – space-filling design: greedily add the candidate whose
                    distance to the nearest chosen point is largest
                    (starts from the point closest to the area centroid).
* ``d_optimal``   – greedy D-optimal design for the planar trend model:
                    maximise det(AᵀA) of the plane design matrix, which pushes
                    points towards the boundary while keeping them spread.

The candidates are restricted to a grid inside the area, mimicking points a
surveyor can actually occupy. Optionally a small random jitter models the
fact that the exact spot is chosen in the field.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon

from .experiment import grid_in_polygon, sample_in_polygon


def _plane_design(p: np.ndarray, c: np.ndarray) -> np.ndarray:
    q = (p - c) / 1000.0
    return np.column_stack([np.ones(len(q)), q[:, 0], q[:, 1]])


def maximin(cands: np.ndarray, n: int, start: np.ndarray | None = None) -> np.ndarray:
    c = cands.mean(axis=0) if start is None else start
    idx = [int(np.argmin(np.hypot(*(cands - c).T)))]
    dmin = np.hypot(*(cands - cands[idx[0]]).T)
    while len(idx) < n:
        k = int(np.argmax(dmin))
        idx.append(k)
        dmin = np.minimum(dmin, np.hypot(*(cands - cands[k]).T))
    return cands[idx]


def d_optimal(cands: np.ndarray, n: int) -> np.ndarray:
    """Greedy D-optimal for a plane, then filled up by maximin spacing."""
    c = cands.mean(axis=0)
    A = _plane_design(cands, c)
    chosen: list[int] = []
    M = 1e-6 * np.eye(3)
    for _ in range(min(n, 3)):
        Minv = np.linalg.inv(M)
        gain = np.einsum("ij,jk,ik->i", A, Minv, A)  # leverage = det increase
        gain[chosen] = -np.inf
        k = int(np.argmax(gain))
        chosen.append(k)
        M = M + np.outer(A[k], A[k])
    # remaining points: maximise det while penalising clustering
    while len(chosen) < n:
        Minv = np.linalg.inv(M)
        gain = np.log1p(np.einsum("ij,jk,ik->i", A, Minv, A))
        dmin = np.min(np.hypot(*(cands[:, None, :] - cands[chosen][None]).transpose(2, 0, 1)),
                      axis=1)
        score = gain * (dmin / (dmin.max() + 1e-9))
        score[chosen] = -np.inf
        k = int(np.argmax(score))
        chosen.append(k)
        M = M + np.outer(A[k], A[k])
    return cands[chosen]


def place(strategy: str, area: Polygon, n: int, rng: np.random.Generator,
          cand_spacing: float, jitter: float = 0.0, min_dist: float = 0.0) -> np.ndarray:
    if strategy == "random":
        return sample_in_polygon(area, n, rng, min_dist)
    cands = grid_in_polygon(area, cand_spacing)
    if strategy == "maximin":
        start = cands[rng.integers(len(cands))]  # random start → variability between runs
        pts = maximin(cands, n, start)
    elif strategy == "d_optimal":
        pts = d_optimal(cands, n)
    else:
        raise ValueError(strategy)
    if jitter:
        pts = pts + rng.normal(0, jitter, pts.shape)
    return pts
