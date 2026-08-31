#!/usr/bin/env python3
"""Render the S6/b post-activation subsidy curve.

Unlike S1/S5/b, S6/b's schedule has no exponential/recursive decay to
sample densely -- it is exactly five flat segments (four fixed-value phases
plus the terminal zero cutoff), so the full schedule is representable by
its own phase-boundary heights directly; there is no "sparse vector file"
plotting hazard here (see independently_derive_s1_schedule.py's docstring
for what that hazard looks like when it does apply). The phase table below
is transcribed from the specification and cross-checked against
analysis/data/S6B_normative_test_vectors.csv and against
analysis/scripts/verify_s6b_independently.py's own derivation -- not
imported from the C++ implementation under test.
"""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "verification" / "figures" / "s6b_subsidy_curve.png"

# (start_height, subsidy_rin) -- matches chainparams.cpp's ForkSubsidyPhases
# for mainnet exactly, and analysis/scripts/verify_s6b_independently.py's
# derive_terminal_height() for the terminal entry.
PHASES = [
    (840000, 4.0),
    (2100000, 2.0),
    (4200000, 1.0),
    (6300000, 0.6),
    (234587500, 0.0),
]
PRE_ACTIVATION = (839999, 6.25)

heights = [PRE_ACTIVATION[0]] + [h for h, _ in PHASES]
subsidy = [PRE_ACTIVATION[1]] + [s for _, s in PHASES]
# Extend the last (zero) segment a little so the step is visible.
heights.append(PHASES[-1][0] + 20000000)
subsidy.append(0.0)

fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(10, 4))

ax_full.step(heights, subsidy, where="post", color="#d97706", linewidth=1.8)
ax_full.set_xlabel("Block height")
ax_full.set_ylabel("Maximum permitted subsidy (RIN)")
ax_full.set_title("Full schedule to the terminal cutoff")
ax_full.axvline(840000, color="#c53030", linestyle="--", linewidth=1, label="H1 = 840,000")
ax_full.axvline(234587500, color="#2b6cb0", linestyle=":", linewidth=1.2, label="terminal cutoff\n(234,587,500, derived)")
ax_full.legend(loc="upper right", fontsize=7)
ax_full.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
ax_full.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:g}M"))

zoom = [(h, s) for h, s in zip(heights, subsidy) if h <= 8000000]
zh = [h for h, _ in zoom]
zs = [s for _, s in zoom]
ax_zoom.step(zh, zs, where="post", color="#d97706", linewidth=1.8, marker="o", markersize=4)
ax_zoom.axvline(840000, color="#c53030", linestyle="--", linewidth=1, label="H1 = 840,000")
ax_zoom.set_xlabel("Block height")
ax_zoom.set_ylabel("Maximum permitted subsidy (RIN)")
ax_zoom.set_title("First four phases\n(the 0.6 RIN phase runs until 234,587,500)")
ax_zoom.legend(loc="upper right", fontsize=8)
ax_zoom.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
ax_zoom.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))

fig.suptitle("S6/b candidate: maximum permitted block subsidy\n"
             "(four fixed-value phases, then a derived cutoff to exactly zero; "
             "cross-checked against verify_s6b_independently.py)",
             fontsize=10)
fig.tight_layout(rect=[0, 0, 1, 0.90])
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=160)
print(f"wrote {OUT}")
