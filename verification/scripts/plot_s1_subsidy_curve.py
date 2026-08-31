#!/usr/bin/env python3
"""Render the S1 post-activation subsidy curve.

Uses the dense, every-epoch series from independently_derive_s1_schedule.py
(run that script first), not analysis/data/S1_normative_test_vectors.csv
directly -- that file is a deliberately *sparse* boundary/threshold vector
set (dense for the first ten epochs, then only threshold-crossing and
terminal points), and plotting it directly with a step function invents fake
multi-million-block flat plateaus between its sparse points. The dense
series is independently re-derived from the publicly documented recursive
rule and cross-checked against every applicable row of the sparse file (see
that script), so this figure still doesn't import or call the Rincoin Core
implementation it verifies.
"""
import csv
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = pathlib.Path(__file__).resolve().parents[2]
DENSE_SCHEDULE = ROOT / "verification" / "data" / "s1_independent_dense_schedule.csv"
OUT = ROOT / "verification" / "figures" / "s1_subsidy_curve.png"

if not DENSE_SCHEDULE.exists():
    raise SystemExit(f"{DENSE_SCHEDULE} missing -- run independently_derive_s1_schedule.py first")

rows = []
with open(DENSE_SCHEDULE, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append((int(r["epoch_start_height"]), float(r["subsidy_rin"])))

# Pre-activation point, so the chart shows the actual pre/post-H1 step too.
rows.insert(0, (839999, 6.25))
rows.sort()
heights = [h for h, _ in rows]
subsidy = [s for _, s in rows]

fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(10, 4))

ax_full.step(heights, subsidy, where="post", color="#2b6cb0", linewidth=1.5)
ax_full.set_yscale("log")
ax_full.set_xlabel("Block height")
ax_full.set_ylabel("Maximum permitted subsidy (RIN, log scale)")
ax_full.set_title("Full schedule to exhaustion")
ax_full.axvline(840000, color="#c53030", linestyle="--", linewidth=1, label="H1 = 840,000")
ax_full.legend(loc="upper right", fontsize=8)
ax_full.grid(True, which="both", linestyle=":", linewidth=0.5, alpha=0.6)
ax_full.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:g}M"))

zoom = [(h, s) for h, s in rows if h <= 840000 + 210000 * 12]
zh = [h for h, _ in zoom]
zs = [s for _, s in zoom]
ax_zoom.step(zh, zs, where="post", color="#2b6cb0", linewidth=1.8, marker="o", markersize=3)
ax_zoom.axvline(840000, color="#c53030", linestyle="--", linewidth=1, label="H1 = 840,000")
ax_zoom.set_xlabel("Block height")
ax_zoom.set_ylabel("Maximum permitted subsidy (RIN)")
ax_zoom.set_title("First 12 post-activation epochs")
ax_zoom.legend(loc="upper right", fontsize=8)
ax_zoom.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
ax_zoom.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.2f}M"))
ax_zoom.tick_params(axis="x", labelrotation=30)

fig.suptitle("S1 candidate: maximum permitted block subsidy\n"
             "(independently re-derived from the published recursive rule; "
             "agrees with all 34 applicable normative vectors)",
             fontsize=10)
fig.tight_layout(rect=[0, 0, 1, 0.92])
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=160)
print(f"wrote {OUT}")
