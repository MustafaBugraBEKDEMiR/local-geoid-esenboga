"""Compare control-point placement strategies (random / maximin / D-optimal).

Usage:  python scripts/run_placement.py [--reps 200]
"""
import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from localgeoid import (KrigingSurface, PolynomialSurface, RemoveRestore,  # noqa: E402
                        load_study_data)
from localgeoid.experiment import grid_in_polygon, region_box  # noqa: E402
from localgeoid.placement import d_optimal, maximin, place  # noqa: E402

OUT = ROOT / "data" / "processed"


def methods(d):
    return [PolynomialSurface(1), KrigingSurface(),
            RemoveRestore(d.n_egm, PolynomialSurface(0), name="EGM2008 + constant shift"),
            RemoveRestore(d.n_egm, KrigingSurface())]


def main(reps: int):
    d = load_study_data()
    c = d.campus_tm.centroid
    areas = {"campus": (d.campus_tm, 50.0, 25.0),
             "region": (region_box((c.x, c.y), 15_000, 14_000), 500.0, 250.0)}
    rows = []
    for sc, (area, cand_sp, jitter) in areas.items():
        chk = grid_in_polygon(area, np.sqrt(area.area / 1500))
        truth = d.n_true(chk[:, 0], chk[:, 1])
        for n in (4, 6, 8, 12):
            rng = np.random.default_rng(3000 + n)
            for strat in ("random", "maximin", "d_optimal"):
                for r in range(reps):
                    cp = place(strat, area, n, rng, cand_sp, jitter=0 if strat == "random" else jitter,
                               min_dist=cand_sp)
                    nobs = d.n_true(cp[:, 0], cp[:, 1]) + rng.normal(0, 0.02, n)
                    for proto in methods(d):
                        m = copy.deepcopy(proto).fit(cp[:, 0], cp[:, 1], nobs)
                        e = m.predict(chk[:, 0], chk[:, 1]) - truth
                        rows.append(dict(scenario=sc, n_points=n, strategy=strat, rep=r,
                                         method=m.name, rmse=float(np.sqrt(np.mean(e**2))),
                                         max_abs=float(np.max(np.abs(e)))))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "placement_results.csv", index=False)
    s = (df.groupby(["scenario", "method", "n_points", "strategy"])
           .agg(rmse_median=("rmse", "median"), rmse_p90=("rmse", lambda x: np.percentile(x, 90)),
                max_abs_p90=("max_abs", lambda x: np.percentile(x, 90)))
           .reset_index())
    s.to_csv(OUT / "placement_summary.csv", index=False)
    t = s[s.n_points == 6].copy()
    t["cell"] = (t.rmse_median * 100).round(1).astype(str) + " / " + (t.rmse_p90 * 100).round(1).astype(str)
    print(t.pivot_table(index=["scenario", "method"], columns="strategy", values="cell", aggfunc="first"))

    # recommended layouts (deterministic) for the 3D viewer / field planning
    rec = []
    for sc, (area, cand_sp, _) in areas.items():
        cands = grid_in_polygon(area, cand_sp)
        for n in (6, 8):
            for strat, pts in (("maximin", maximin(cands, n)), ("d_optimal", d_optimal(cands, n))):
                for i, (x, y) in enumerate(pts, 1):
                    rec.append(dict(scenario=sc, n_points=n, strategy=strat, id=f"P{i}", x=x, y=y))
    pd.DataFrame(rec).to_csv(OUT / "recommended_layouts.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    main(ap.parse_args().reps)
