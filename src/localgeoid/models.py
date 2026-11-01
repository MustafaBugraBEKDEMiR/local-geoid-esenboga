"""Geoid surface models.

Every model follows the same tiny interface::

    model.fit(x, y, n)        # control points (TM33 metres, geoid height m)
    model.predict(x, y) -> n  # geoid height at new points

``RemoveRestore`` wraps any surface model: it removes a global model
(EGM2008) from the observations, models only the residual, and restores the
global model at prediction time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.interpolate import RBFInterpolator


# ---------------------------------------------------------------------------
# Polynomial surfaces solved by least squares (classic "geometric" approach)
# ---------------------------------------------------------------------------
_TERMS = {
    0: ["1"],
    1: ["1", "x", "y"],
    2: ["1", "x", "y", "x2", "xy", "y2"],
    3: ["1", "x", "y", "x2", "xy", "y2", "x3", "x2y", "xy2", "y3"],
}


def _design(xs: np.ndarray, ys: np.ndarray, degree: int) -> np.ndarray:
    cols = {
        "1": np.ones_like(xs),
        "x": xs, "y": ys,
        "x2": xs**2, "xy": xs * ys, "y2": ys**2,
        "x3": xs**3, "x2y": xs**2 * ys, "xy2": xs * ys**2, "y3": ys**3,
    }
    return np.column_stack([cols[t] for t in _TERMS[degree]])


@dataclass
class PolynomialSurface:
    """N(x, y) = sum a_ij x^i y^j with coordinates centred and scaled to km.

    The same centring is used for fitting and prediction (the original
    coursework used opposite signs for the two steps, which flipped the
    linear terms).
    """

    degree: int = 2
    name: str = ""
    params_: np.ndarray = field(default=None, repr=False)
    cov_: np.ndarray = field(default=None, repr=False)
    m0_: float = np.nan
    residuals_: np.ndarray = field(default=None, repr=False)

    def __post_init__(self):
        self.name = self.name or {0: "Constant", 1: "Plane", 2: "Quadratic", 3: "Cubic"}[self.degree]

    @property
    def n_params(self) -> int:
        return len(_TERMS[self.degree])

    def _scaled(self, x, y):
        return (np.asarray(x) - self.x0_) / 1000.0, (np.asarray(y) - self.y0_) / 1000.0

    def fit(self, x, y, n):
        x, y, n = map(np.asarray, (x, y, n))
        if len(n) < self.n_params:
            raise ValueError(f"{self.name} needs >= {self.n_params} points, got {len(n)}")
        self.x0_, self.y0_ = x.mean(), y.mean()
        A = _design(*self._scaled(x, y), self.degree)
        self.params_, *_ = np.linalg.lstsq(A, n, rcond=None)
        v = n - A @ self.params_
        self.residuals_ = v
        dof = len(n) - self.n_params
        self.m0_ = float(np.sqrt(v @ v / dof)) if dof > 0 else np.nan
        if dof > 0:
            self.cov_ = self.m0_**2 * np.linalg.inv(A.T @ A)
        return self

    def predict(self, x, y):
        xs, ys = self._scaled(x, y)
        shape = np.shape(xs)
        A = _design(np.ravel(xs), np.ravel(ys), self.degree)
        return (A @ self.params_).reshape(shape)

    def t_statistics(self) -> np.ndarray:
        """t-values of the coefficients (for significance testing)."""
        return self.params_ / np.sqrt(np.diag(self.cov_))


# ---------------------------------------------------------------------------
# Interpolators
# ---------------------------------------------------------------------------
@dataclass
class RBFSurface:
    """Thin-plate-spline radial basis functions with optional smoothing."""

    smoothing: float = 0.0
    name: str = "Thin-plate spline"

    def fit(self, x, y, n):
        self.x0_, self.y0_ = np.mean(x), np.mean(y)
        P = np.c_[(np.asarray(x) - self.x0_) / 1000, (np.asarray(y) - self.y0_) / 1000]
        self.rbf_ = RBFInterpolator(P, np.asarray(n), kernel="thin_plate_spline",
                                    smoothing=self.smoothing, degree=1)
        return self

    def predict(self, x, y):
        shape = np.shape(x)
        P = np.c_[(np.ravel(x) - self.x0_) / 1000, (np.ravel(y) - self.y0_) / 1000]
        return self.rbf_(P).reshape(shape)


@dataclass
class KrigingSurface:
    """Ordinary kriging (PyKrige) with a linear variogram.

    With few control points a fitted variogram is unstable, so the linear
    model is the robust default; it can be changed via ``variogram``.
    """

    variogram: str = "linear"
    name: str = "Ordinary kriging"

    def fit(self, x, y, n):
        from pykrige.ok import OrdinaryKriging

        self.x0_, self.y0_ = np.mean(x), np.mean(y)
        self.ok_ = OrdinaryKriging(
            (np.asarray(x) - self.x0_) / 1000, (np.asarray(y) - self.y0_) / 1000, np.asarray(n),
            variogram_model=self.variogram, verbose=False, enable_plotting=False,
        )
        return self

    def predict(self, x, y):
        shape = np.shape(x)
        z, _ = self.ok_.execute("points", (np.ravel(x) - self.x0_) / 1000,
                                (np.ravel(y) - self.y0_) / 1000)
        return np.asarray(z).reshape(shape)


# ---------------------------------------------------------------------------
# Global model alone and remove–compute–restore
# ---------------------------------------------------------------------------
@dataclass
class GlobalModelOnly:
    """Use the global model directly (what a GNSS receiver does by default)."""

    global_n: Callable
    name: str = "EGM2008 only"

    def fit(self, x, y, n):
        return self

    def predict(self, x, y):
        return self.global_n(x, y)


@dataclass
class RemoveRestore:
    """N = N_global + residual surface fitted to (N_obs - N_global)."""

    global_n: Callable
    surface: object
    name: str = ""

    def __post_init__(self):
        self.name = self.name or f"EGM2008 + {self.surface.name.lower()}"

    def fit(self, x, y, n):
        self.surface.fit(x, y, np.asarray(n) - self.global_n(x, y))
        return self

    def predict(self, x, y):
        return self.global_n(x, y) + self.surface.predict(x, y)
