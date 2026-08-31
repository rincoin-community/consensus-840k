#!/usr/bin/env python3
"""Independent re-derivation of the S1 post-activation subsidy schedule.

This computes the full, dense, per-epoch schedule from the recursive rule as
published in technology/consensus-transition.md and restated in the
"expected_rule" column of every row of
analysis/data/S1_normative_test_vectors.csv ("floor(previous_epoch_subsidy *
19 / 20)", one step per 210,000-block epoch from height 840,000, starting
from the pre-activation subsidy at height 839,999). It does not import or
call the C++ implementation under test (src/validation.cpp) or the analysis
package's own simulator (scripts/simulate_monetary_scenarios.py) -- it is a
second, independent implementation of the same publicly stated rule, in the
spirit of scripts/verify_s6b_independently.py's existing role for S6/b.

analysis/data/S1_normative_test_vectors.csv is a *sparse* boundary/threshold
vector file by design (dense for the first ten post-activation epochs, then
only threshold-crossing and terminal points -- see that file's own header
comment in the specification). It is the right file to spot-check exact
values against, but plotting it directly with a step function invents fake
multi-million-block flat plateaus between its sparse points, followed by
sudden drops that do not exist in the actual schedule. This script produces
the dense, every-epoch series a chart actually needs, and cross-checks it
against every row of the sparse file as a consistency check.
"""
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS = ROOT / "analysis" / "data" / "S1_normative_test_vectors.csv"
OUT_CSV = ROOT / "verification" / "data" / "s1_independent_dense_schedule.csv"
OUT_JSON = ROOT / "verification" / "data" / "s1_independent_dense_schedule.json"

H1 = 840000
EPOCH_LENGTH = 210000
PRE_ACTIVATION_SUBSIDY = 625000000  # height 839,999, unchanged legacy rule


def derive_dense_schedule():
    """floor(previous_epoch_subsidy * 19 / 20) per epoch, starting from the
    pre-activation value, until the subsidy reaches zero."""
    rows = []
    subsidy = PRE_ACTIVATION_SUBSIDY
    epoch = 0
    while True:
        subsidy = (subsidy * 19) // 20
        height = H1 + epoch * EPOCH_LENGTH
        rows.append((height, epoch + 1, subsidy))
        epoch += 1
        if subsidy == 0:
            break
    return rows


def cross_check_against_sparse_vectors(dense_by_height):
    mismatches = []
    checked = 0
    with open(VECTORS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            height = int(r["height"])
            if height < H1:
                continue  # pre-activation rows use the unchanged legacy rule, not this schedule
            expected = int(r["maximum_permitted_subsidy_base_units"])
            # Sparse rows include both the first and last block of an epoch;
            # the subsidy is constant within an epoch, so look up by epoch
            # start height.
            epoch_start = H1 + ((height - H1) // EPOCH_LENGTH) * EPOCH_LENGTH
            actual = dense_by_height.get(epoch_start)
            checked += 1
            if actual != expected:
                mismatches.append((r["vector_id"], height, expected, actual))
    return checked, mismatches


if __name__ == "__main__":
    dense = derive_dense_schedule()
    dense_by_height = {h: s for h, _, s in dense}

    checked, mismatches = cross_check_against_sparse_vectors(dense_by_height)
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
        w.writerow(["epoch_start_height", "epoch_number", "subsidy_base_units", "subsidy_rin"])
        for h, e, s in dense:
            w.writerow([h, e, s, f"{s / 1e8:.8f}"])
    OUT_JSON.write_text(json.dumps(
        [{"epoch_start_height": h, "epoch_number": e, "subsidy_base_units": s} for h, e, s in dense],
        indent=2), encoding="utf-8")
    print(f"wrote {OUT_CSV} and {OUT_JSON} ({len(dense)} epochs)")
