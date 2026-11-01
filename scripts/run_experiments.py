"""Run the Monte-Carlo method comparison and write results to data/processed.

Usage:  python scripts/run_experiments.py [--reps 200]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from localgeoid import load_study_data  # noqa: E402
from localgeoid.experiment import Scenario, region_box, run_scenario  # noqa: E402

OUT = ROOT / "data" / "processed"


def main(reps: int):
    OUT.mkdir(parents=True, exist_ok=True)
    d = load_study_data()
    c = d.campus_tm.centroid
    areas = {
        "campus": (d.campus_tm, 50.0),
        # 15 x 14 km box centred on the campus (same extent as the original coursework area)
        "region": (region_box((c.x, c.y), 15_000, 14_000), 1500.0),
    }
    frames = []
    for name, (area, min_dist) in areas.items():
        for n in (4, 6, 8, 12, 20):
            frames.append(run_scenario(d, Scenario(name, area, n, 0.02, min_dist), reps=reps,
                                       seed=1000 + n))
        for noise in (0.005, 0.01, 0.03, 0.05):
            frames.append(run_scenario(d, Scenario(name, area, 8, noise, min_dist), reps=reps,
                                       seed=2000 + int(noise * 1000)))
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(OUT / "mc_results.csv", index=False)

    summary = (df.groupby(["scenario", "noise_m", "n_points", "method"])
                 .agg(rmse_median=("rmse", "median"),
                      rmse_p90=("rmse", lambda s: np.percentile(s, 90)),
                      bias_median=("bias", "median"),
                      runs=("rmse", "size"))
                 .reset_index())
    summary.to_csv(OUT / "mc_summary.csv", index=False)
    main_tbl = summary[(summary.noise_m == 0.02) & (summary.n_points == 8)]
    print((main_tbl.sort_values(["scenario", "rmse_median"])
           .assign(rmse_cm=lambda t: (t.rmse_median * 100).round(1),
                   p90_cm=lambda t: (t.rmse_p90 * 100).round(1))
           [["scenario", "method", "rmse_cm", "p90_cm"]].to_string(index=False)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    main(ap.parse_args().reps)
