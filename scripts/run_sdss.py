"""Run the campus SDSS scenario (TG-20 vs EGM2008) and save the results.

Usage:  python scripts/run_sdss.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from localgeoid import load_study_data  # noqa: E402
from localgeoid.sdss import evaluate, summary, sweep  # noqa: E402

OUT = ROOT / "data" / "processed"
d = load_study_data()
osm = json.loads((ROOT / "data/raw/osm_campus_features.json").read_text(encoding="utf-8"))["elements"]
res = evaluate(d, osm)
s = summary(res)
sc = res["scenario"]
s["scenario"] = {k: v for k, v in sc.__dict__.items()}
s["manhole_H_m"] = round(res["manhole"][2], 2)
s["manhole_invert_m"] = round(res["manhole"][3], 2)
(OUT / "sdss_summary.json").write_text(json.dumps(s, indent=2, default=float), encoding="utf-8")
offs = np.arange(-15, 15.5, 0.5)
pd.DataFrame({"threshold_shift_m": offs, "flip_pct_rule_A": sweep(res, "A", offs),
              "flip_pct_rule_B": sweep(res, "B", offs)}).round(3).to_csv(OUT / "sdss_sweep.csv", index=False)
print(json.dumps(s, indent=2, default=float))
