#!/usr/bin/env python3
"""Independent re-derivation of the S5/b post-activation subsidy schedule.

Computes the full, dense, per-epoch schedule from the formula as published
in analysis/Rincoin_840k_S5B_Consensus_Change_Specification.qmd:
Subsidy(h) = 625,000,000 >> n, where n = floor((h - 630000) / 2100000),
zero once n >= 30. It does not import or call the C++ implementation under
test (src/validation.cpp) or the analysis package's own simulator
(scripts/simulate_monetary_scenarios.py) -- it is a second, independent
implementation of the same publicly stated rule, in the spirit of
scripts/verify_s6b_independently.py's existing role for S6/b and this
project's own independently_derive_s1_schedule.py for S1.

analysis/data/S5B_normative_test_vectors.csv is a *sparse* boundary/
threshold vector file by design (dense for the first ten post-activation
epochs, then only threshold-crossing and terminal points). It is the right
file to spot-check exact values against, but plotting it directly with a
step function invents fake flat plateaus between its sparse points -- see
independently_derive_s1_schedule.py's own docstring for the fuller
rationale (the same mistake was made and fixed for S1's figure). This
script produces the dense, every-epoch series a chart actually needs, and
cross-checks it against every row of the sparse file as a consistency
check.
"""
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS = ROOT / "analysis" / "data" / "S5B_normative_test_vectors.csv"
OUT_CSV = ROOT / "verification" / "data" / "s5b_independent_dense_schedule.csv"
OUT_JSON = ROOT / "verification" / "data" / "s5b_independent_dense_schedule.json"

H1 = 840000
HALVING_INTERVAL = 210000
ANCHOR = H1 - HALVING_INTERVAL  # 630,000
POST_FORK_EPOCH_LENGTH = 10 * HALVING_INTERVAL  # 2,100,000
PRE_ACTIVATION_SUBSIDY_AT_ANCHOR_EPOCH = 625000000  # base value at height 839,999, unchanged legacy rule
MAX_PHASE = 30  # phase >= 30 -> zero (625,000,000 >> 30 == 0, matching the spec's own clause)


def derive_dense_schedule():
    """base >> phase per phase, phase = floor((h - ANCHOR) / POST_FORK_EPOCH_LENGTH),
    starting at phase 0 (height ANCHOR) through phase MAX_PHASE (first zero)."""
    rows = []
    for phase in range(MAX_PHASE + 1):
        height = ANCHOR + phase * POST_FORK_EPOCH_LENGTH
        subsidy = PRE_ACTIVATION_SUBSIDY_AT_ANCHOR_EPOCH >> phase if phase < MAX_PHASE else 0
        rows.append((height, phase, subsidy))
    return rows


def cross_check_against_sparse_vectors(dense_by_phase_start):
    mismatches = []
    checked = 0
    with open(VECTORS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            height = int(r["height"])
            if height < H1:
                continue  # pre-activation rows use the unchanged legacy rule, not this schedule
            expected = int(r["maximum_permitted_subsidy_base_units"])
            phase = (height - ANCHOR) // POST_FORK_EPOCH_LENGTH
            phase_start = ANCHOR + phase * POST_FORK_EPOCH_LENGTH
            actual = dense_by_phase_start.get(phase_start)
            if actual is None:
                actual = 0 if phase >= MAX_PHASE else None
            checked += 1
            if actual != expected:
                mismatches.append((r["vector_id"], height, expected, actual))
    return checked, mismatches


if __name__ == "__main__":
    dense = derive_dense_schedule()
    dense_by_phase_start = {h: s for h, _, s in dense}

    checked, mismatches = cross_check_against_sparse_vectors(dense_by_phase_start)
    if mismatches:
        raise SystemExit(
            f"independent re-derivation DISAGREES with "
            f"{len(mismatches)}/{checked} normative vectors: {mismatches[:5]}"
        )
    print(f"independent re-derivation agrees with all {checked} applicable "
          f"normative vectors in {VECTORS.name}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phase_start_height", "phase_number", "subsidy_base_units", "subsidy_rin"])
        for h, p, s in dense:
            w.writerow([h, p, s, f"{s / 1e8:.8f}"])
    OUT_JSON.write_text(json.dumps(
        [{"phase_start_height": h, "phase_number": p, "subsidy_base_units": s} for h, p, s in dense],
        indent=2), encoding="utf-8")
    print(f"wrote {OUT_CSV} and {OUT_JSON} ({len(dense)} phases)")
