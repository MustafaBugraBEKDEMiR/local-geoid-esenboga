"""Produce the figures in ./figures from the raw data and the MC results."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.interpolate import griddata  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

from localgeoid import load_study_data  # noqa: E402
from localgeoid.data import lonlat_to_tm  # noqa: E402
from localgeoid.experiment import region_box  # noqa: E402

FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)

# reference palette (dataviz skill, light mode)
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
SERIES = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a",
          "violet": "#6250d6", "red": "#e34948"}
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.spines.top": False,
    "axes.spines.right": False, "figure.dpi": 150, "savefig.bbox": "tight",
})

d = load_study_data()
osm = json.loads((ROOT / "data/raw/osm_campus_features.json").read_text(encoding="utf-8"))["elements"]
ROAD_CLS = ("tertiary", "unclassified", "residential")


def km(ax, dec=0, ylabel=True):
    ax.set_xlabel("Easting, TUREF/TM33 (km)")
    if ylabel:
        ax.set_ylabel("Northing (km)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v/1000:.{dec}f}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v/1000:.{dec}f}")


def draw_campus(ax, lw=1.6):
    x, y = d.campus_tm.exterior.xy
    ax.plot(x, y, color=INK, lw=lw)


# ---------------------------------------------------------------- Fig 1
c = d.campus_tm.centroid
reg = region_box((c.x, c.y), 15_000, 14_000)
minx, miny, maxx, maxy = reg.bounds
X, Y = np.meshgrid(np.linspace(minx, maxx, 160), np.linspace(miny, maxy, 150))
NT, NE = d.n_true(X, Y), d.n_egm(X, Y)

fig, axs = plt.subplots(1, 2, figsize=(11, 4.6))
cs = axs[0].contourf(X, Y, NT, levels=14, cmap="Blues")
axs[0].contour(X, Y, NT, levels=14, colors="white", linewidths=0.4)
fig.colorbar(cs, ax=axs[0], label="N (m)", shrink=0.85)
axs[0].set_title("TG-20 geoid height, 15 × 14 km around the campus")
diff = (NE - NT) * 100
cs = axs[1].contourf(X, Y, diff, levels=14, cmap="Oranges")
fig.colorbar(cs, ax=axs[1], label="EGM2008 − TG-20 (cm)", shrink=0.85)
axs[1].set_title("Error of using EGM2008 directly")
for i, ax in enumerate(axs):
    draw_campus(ax)
    ax.set_aspect("equal")
    km(ax, ylabel=(i == 0))
axs[0].annotate("AYBÜ Esenboğa\ncampus", (c.x, c.y), (c.x + 2500, c.y + 3500), color=INK,
                arrowprops=dict(arrowstyle="-", color=INK, lw=0.8), fontsize=9)
fig.savefig(FIG / "fig1_region_geoid.png")
plt.close(fig)

# ---------------------------------------------------------------- Fig 2
pad = 250
minx, miny, maxx, maxy = d.campus_tm.buffer(pad).bounds
X, Y = np.meshgrid(np.linspace(minx, maxx, 220), np.linspace(miny, maxy, 160))
H = griddata((d.srtm.x, d.srtm.y), d.srtm.H_srtm, (X, Y), method="cubic")
fig, ax = plt.subplots(figsize=(10, 6))
cs = ax.contourf(X, Y, H, levels=np.arange(930, 995, 5), cmap="Greys", alpha=0.55)
fig.colorbar(cs, ax=ax, label="Terrain height, SRTM 30 m (m)", shrink=0.8)
NT = d.n_true(X, Y) * 100
cl = ax.contour(X, Y, NT, levels=np.arange(np.floor(NT.min()), NT.max(), 1),
                colors=SERIES["blue"], linewidths=1.0)
ax.clabel(cl, fmt=lambda v: f"{v/100:.2f}", fontsize=8)
for f in osm:
    g = np.array(f["g"])
    gx, gy = lonlat_to_tm(g[:, 0], g[:, 1])
    if "building" in f["tags"]:
        ax.fill(gx, gy, color=SERIES["orange"], lw=0)
    elif f["tags"].get("highway") in ROAD_CLS:
        ax.plot(gx, gy, color=INK2, lw=1.2)
draw_campus(ax)
ax.set_aspect("equal")
km(ax, dec=1)
ax.set_title("Campus: terrain, buildings (OSM) and TG-20 geoid contours (m, 1 cm interval)")
fig.savefig(FIG / "fig2_campus_map.png")
plt.close(fig)

# ---------------------------------------------------------------- Fig 3
s = pd.read_csv(ROOT / "data/processed/mc_summary.csv")
s = s[s.noise_m == 0.02]
show = [("Plane", SERIES["blue"]), ("Quadratic", SERIES["red"]),
        ("Ordinary kriging", SERIES["aqua"]), ("EGM2008 + constant shift", SERIES["orange"]),
        ("EGM2008 + ordinary kriging", SERIES["violet"])]
fig, axs = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
for ax, sc, title in zip(axs, ["campus", "region"], ["Campus (≈1.7 km²)", "Region (15 × 14 km)"]):
    t = s[s.scenario == sc]
    for name, col in show:
        u = t[t.method == name].sort_values("n_points")
        ax.plot(u.n_points, u.rmse_median * 100, "-o", color=col, lw=2, ms=6, label=name)
    egm = t[t.method == "EGM2008 only"].rmse_median.iloc[0] * 100
    ax.axhline(egm, color=MUTED, ls="--", lw=1.2)
    ax.text(20, egm * 0.82, f"EGM2008 only: {egm:.0f} cm", ha="right", color=INK2, fontsize=9)
    ax.axhline(2, color=GRID, lw=1)
    ax.set_yscale("log")
    ax.set_xticks([4, 6, 8, 12, 20])
    ax.set_xlabel("Number of GNSS/levelling control points")
    ax.set_title(title)
    ax.grid(axis="y", color=GRID, lw=0.6)
axs[0].set_ylabel("RMSE vs TG-20 (cm, log scale; median of 200 runs)")
axs[0].yaxis.set_major_formatter(lambda v, _: f"{v:g}")
fig.legend(*axs[0].get_legend_handles_labels(), frameon=False, fontsize=9, ncol=5,
           loc="lower center", bbox_to_anchor=(0.5, -0.06))
fig.suptitle("Accuracy of local geoid methods (control-point noise σ = 2 cm)", color=INK,
             fontweight="bold")
fig.savefig(FIG / "fig3_method_comparison.png")
plt.close(fig)

# ---------------------------------------------------------------- Fig 4
# main campus road: western tertiary (w863372672) + northern tertiary (w863372675)
road = [next(f for f in osm if f["id"] == i) for i in ("w863372672", "w863372675")]
pts = np.vstack([np.array(road[0]["g"]), np.array(road[1]["g"])[1:]])
rx, ry = lonlat_to_tm(pts[:, 0], pts[:, 1])
line = LineString(np.c_[rx, ry])
dist = np.arange(0, line.length, 10.0)
P = np.array([line.interpolate(t).coords[0] for t in dist])
Hr = griddata((d.srtm.x, d.srtm.y), d.srtm.H_srtm, (P[:, 0], P[:, 1]), method="linear")
nt, ne = d.n_true(P[:, 0], P[:, 1]), d.n_egm(P[:, 0], P[:, 1])
err = (nt - ne)  # H_egm - H_true = (h - N_egm) - (h - N_tg20)
fig, axs = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True,
                        gridspec_kw=dict(height_ratios=[1.3, 1]))
axs[0].plot(dist, Hr, color=INK2, lw=2)
axs[0].set_ylabel("Terrain H (m)")
axs[0].set_title(f"Main campus road ({line.length/1000:.1f} km): what EGM2008 does to GNSS heights")
axs[1].plot(dist, err * 100, color=SERIES["orange"], lw=2)
axs[1].set_ylabel("H error (cm)")
axs[1].set_xlabel("Distance along road (m)")
axs[1].set_ylim(min(-40, err.min() * 110), 0)
axs[1].text(dist[-1], err.mean() * 100 + 3,
            f"constant offset ≈ {err.mean()*100:.0f} cm;  slope error ≤ "
            f"{np.max(np.abs(np.gradient(err, dist)))*1000:.3f} ‰", ha="right", color=INK)
for ax in axs:
    ax.grid(axis="y", color=GRID, lw=0.6)
fig.savefig(FIG / "fig4_road_profile_error.png")
plt.close(fig)

print("road length", line.length, "offset mean", err.mean(), "range", np.ptp(err),
      "max slope err permille", np.max(np.abs(np.gradient(err, dist))) * 1000)
print("campus N_TG20 range (cm)", np.ptp(d.n_true(X, Y)) * 100)

# ---------------------------------------------------------------- Fig 5 placement
pp = ROOT / "data/processed/placement_summary.csv"
if pp.exists():
    ps = pd.read_csv(pp)
    lay = pd.read_csv(ROOT / "data/processed/recommended_layouts.csv")
    strat_col = {"random": MUTED, "maximin": SERIES["blue"], "d_optimal": SERIES["orange"]}
    strat_lbl = {"random": "Random", "maximin": "Space-filling (maximin)", "d_optimal": "D-optimal (plane)"}
    fig, axs = plt.subplots(1, 3, figsize=(14, 4.4), gridspec_kw=dict(width_ratios=[1, 1, 1.15]))
    for ax, sc, meth, title in [(axs[0], "campus", "Plane", "Campus · plane"),
                                (axs[1], "region", "Ordinary kriging", "Region · kriging")]:
        t = ps[(ps.scenario == sc) & (ps.method == meth)]
        for st, col in strat_col.items():
            u = t[t.strategy == st].sort_values("n_points")
            ax.plot(u.n_points, u.rmse_median * 100, "-o", color=col, lw=2, ms=6, label=strat_lbl[st])
            ax.plot(u.n_points, u.rmse_p90 * 100, "--", color=col, lw=1.2)
        ax.set_xticks([4, 6, 8, 12])
        ax.set_xlabel("Control points")
        ax.set_title(title)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_ylim(0, None)
    axs[0].set_ylabel("RMSE (cm)  — solid: median, dashed: 90th pct.")
    axs[0].legend(frameon=False, fontsize=9)
    ax = axs[2]
    x, y = d.campus_tm.exterior.xy
    ax.fill(x, y, color="#f1f0ec", ec=INK, lw=1.4)
    for st, mk in (("maximin", "o"), ("d_optimal", "s")):
        u = lay[(lay.scenario == "campus") & (lay.n_points == 8) & (lay.strategy == st)]
        ax.scatter(u.x, u.y, s=60, marker=mk, color=strat_col[st], ec="white", lw=1.5,
                   label=strat_lbl[st], zorder=3)
    ax.set_aspect("equal")
    km(ax, dec=1)
    ax.set_title("Suggested 8-point layouts on campus")
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2)
    fig.suptitle("Planned placement mainly removes bad surveys (90th percentile)", color=INK,
                 fontweight="bold")
    fig.savefig(FIG / "fig5_placement.png")
    plt.close(fig)

# ---------------------------------------------------------------- Fig 7 SDSS scenario
from matplotlib.colors import ListedColormap  # noqa: E402

from localgeoid.sdss import evaluate  # noqa: E402

res = evaluate(d, osm)
sw = pd.read_csv(ROOT / "data/processed/sdss_sweep.csv")
cmap = ListedColormap(["#ffffff", "#e4e3df", "#b9b6ae", SERIES["aqua"], SERIES["orange"], SERIES["red"]])
fig, axs = plt.subplots(1, 3, figsize=(16, 4.8), gridspec_kw=dict(width_ratios=[1, 1, 0.9]))
for ax, k, title, bad, badlbl in [
        (axs[0], "A", "Rule A — gravity sewer connection", "lost", "valid, but rejected with EGM2008"),
        (axs[1], "B", "Rule B — absolute height limit", "wrongly_ok", "invalid, but accepted with EGM2008")]:
    r = res[k]
    code = np.zeros(res["X"].shape, int)
    code[res["inside"]] = 1                       # excluded by site constraints
    code[res["site_ok"]] = 2                      # fails the rule in both runs
    code[r["ref"] & r["egm"]] = 3                 # suitable in both
    code[r[bad]] = 4 if bad == "lost" else 5
    ext = [res["X"].min(), res["X"].max(), res["Y"].min(), res["Y"].max()]
    ax.imshow(code, origin="lower", extent=ext, cmap=cmap, vmin=0, vmax=5, interpolation="nearest")
    draw_campus(ax, lw=1.2)
    if k == "A":
        mx, my = res["manhole"][:2]
        ax.plot(mx, my, "v", color=INK, ms=9)
        ax.annotate("manhole", (mx, my), (mx - 520, my - 120), fontsize=9, color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK, lw=.8))
    ax.set_aspect("equal")
    km(ax, dec=1, ylabel=(k == "A"))
    ax.set_title(title)
    n_bad = r[bad].sum() * res["scenario"].cell ** 2 / 1e4
    from matplotlib.patches import Patch  # noqa: E402
    ax.legend(handles=[Patch(color="#e4e3df", label="excluded (slope, near buildings, far from road…)"),
                       Patch(color="#b9b6ae", label="fails rule (both geoids)"),
                       Patch(color=SERIES["aqua"], label="suitable (both geoids)"),
                       Patch(color=SERIES["orange"] if bad == "lost" else SERIES["red"],
                             label=f"{badlbl}: {n_bad:.2f} ha")],
              frameon=False, fontsize=8.5, loc="upper left", bbox_to_anchor=(0.0, -0.16), ncol=1)
ax = axs[2]
ax.plot(sw.threshold_shift_m, sw.flip_pct_rule_A, color=SERIES["orange"], lw=2, label="Rule A (sewer)")
ax.plot(sw.threshold_shift_m, sw.flip_pct_rule_B, color=SERIES["red"], lw=2, label="Rule B (height limit)")
ax.axvline(0, color=MUTED, ls="--", lw=1)
ax.text(0.3, 0.05, "scenario\nvalue", color=INK2, fontsize=9, transform=ax.get_xaxis_transform())
ax.set_xlabel("Shift of the rule threshold (m)")
ax.set_ylabel("Eligible area whose decision flips (%)")
ax.set_title("Sensitivity to the threshold")
ax.grid(axis="y", color=GRID, lw=0.6)
ax.legend(frameon=False, fontsize=9, loc="upper left")
fig.suptitle("Same campus, same data, only the geoid differs: TG-20 vs EGM2008 (hypothetical thresholds)",
             color=INK, fontweight="bold")
fig.savefig(FIG / "fig7_sdss_scenario.png")
plt.close(fig)
