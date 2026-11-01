import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from localgeoid import (GlobalModelOnly, KrigingSurface, PolynomialSurface, RBFSurface,  # noqa: E402
                        RemoveRestore, load_study_data)

rng = np.random.default_rng(0)
X = 495_000 + rng.uniform(-7000, 7000, 30)
Y = 4_444_000 + rng.uniform(-7000, 7000, 30)


def quad(x, y):
    a, b = (x - 495_000) / 1000, (y - 4_444_000) / 1000
    return 36.8 + 0.012 * a - 0.008 * b + 0.0004 * a * a - 0.0002 * a * b + 0.0003 * b * b


def test_quadratic_recovers_exact_surface():
    m = PolynomialSurface(2).fit(X, Y, quad(X, Y))
    xt, yt = np.array([490_100.0, 499_000.0]), np.array([4_440_500.0, 4_447_000.0])
    assert np.allclose(m.predict(xt, yt), quad(xt, yt), atol=1e-9)
    assert m.m0_ < 1e-9


def test_linear_terms_keep_their_sign():
    """Regression for the original coursework bug (centring sign flip)."""
    n = 30.0 + 0.1 * (X - X.mean()) / 1000
    m = PolynomialSurface(1).fit(X, Y, n)
    assert m.params_[1] == pytest.approx(0.1, abs=1e-9)
    assert m.predict(X.mean() + 1000, Y.mean()) == pytest.approx(30.1, abs=1e-9)


def test_too_few_points_raises():
    with pytest.raises(ValueError):
        PolynomialSurface(2).fit(X[:5], Y[:5], quad(X[:5], Y[:5]))


@pytest.mark.parametrize("model", [RBFSurface(), KrigingSurface()])
def test_interpolators_reproduce_control_points(model):
    n = quad(X, Y)
    model.fit(X, Y, n)
    assert np.allclose(model.predict(X, Y), n, atol=5e-3)


def test_remove_restore_with_perfect_global_model():
    rr = RemoveRestore(quad, PolynomialSurface(0)).fit(X, Y, quad(X, Y) + 0.3)
    assert np.allclose(rr.predict(X, Y), quad(X, Y) + 0.3)
    assert np.allclose(GlobalModelOnly(quad).predict(X, Y), quad(X, Y))


def test_study_data_values_are_plausible():
    d = load_study_data()
    c = d.campus_tm.centroid
    assert 1.5e6 < d.campus_tm.area < 1.9e6          # ~1.7 km2
    assert 36.80 < float(d.n_true(c.x, c.y)) < 36.95   # TG-20 at campus
    assert 37.15 < float(d.n_egm(c.x, c.y)) < 37.25    # EGM2008 at campus


def test_placement_designs_are_spread_and_inside():
    from shapely.geometry import Point

    from localgeoid.experiment import grid_in_polygon
    from localgeoid.placement import d_optimal, maximin

    d = load_study_data()
    cands = grid_in_polygon(d.campus_tm, 50.0)
    for pts in (maximin(cands, 8), d_optimal(cands, 8)):
        assert len(pts) == 8
        assert all(d.campus_tm.contains(Point(*p)) for p in pts)
        dist = np.hypot(*(pts[:, None, :] - pts[None]).transpose(2, 0, 1))
        assert dist[np.triu_indices(8, 1)].min() > 150   # well spread on a ~2 km campus
