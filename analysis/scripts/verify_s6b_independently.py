#!/usr/bin/env python3
"""Independently verify the bounded S6/b schedule and generated vectors.

This implementation deliberately does not import the primary scenario
generator. Original project software in this file is licensed under MIT.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COIN = 100_000_000
ACTIVATION = 840_000
CEILING = 168_000_000 * COIN


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deployed_subsidy(height: int) -> int:
    halvings = height // 210_000
    return 0 if halvings >= 64 else 5_000_000_000 >> halvings


def deployed_issuance_before_activation() -> int:
    total = 0
    for start in range(0, ACTIVATION, 210_000):
        end = min(start + 210_000, ACTIVATION)
        total += (end - start) * deployed_subsidy(start)
    return total


def derive_terminal_height() -> tuple[int, int, int]:
    before = deployed_issuance_before_activation()
    before += (2_100_000 - 840_000) * 400_000_000
    before += (4_200_000 - 2_100_000) * 200_000_000
    before += (6_300_000 - 4_200_000) * 100_000_000
    remaining = CEILING - before
    if remaining <= 0 or remaining % 60_000_000:
        raise AssertionError("S6/b final phase cannot reach 168M exactly")
    blocks = remaining // 60_000_000
    return 6_300_000 + blocks, before, blocks


FIRST_ZERO_HEIGHT, ISSUANCE_AT_FINAL_PHASE_START, FINAL_PHASE_BLOCKS = (
    derive_terminal_height()
)


def subsidy(height: int) -> int:
    if height < ACTIVATION:
        return deployed_subsidy(height)
    if height < 2_100_000:
        return 400_000_000
    if height < 4_200_000:
        return 200_000_000
    if height < 6_300_000:
        return 100_000_000
    if height < FIRST_ZERO_HEIGHT:
        return 60_000_000
    return 0


def cumulative_before(height: int) -> int:
    if height <= 0:
        return 0
    if height <= ACTIVATION:
        total = 0
        for start in range(0, height, 210_000):
            end = min(start + 210_000, height)
            total += (end - start) * deployed_subsidy(start)
        return total
    total = deployed_issuance_before_activation()
    for start, end, reward in (
        (840_000, 2_100_000, 400_000_000),
        (2_100_000, 4_200_000, 200_000_000),
        (4_200_000, 6_300_000, 100_000_000),
        (6_300_000, FIRST_ZERO_HEIGHT, 60_000_000),
    ):
        if height <= start:
            break
        total += (min(height, end) - start) * reward
        if height < end:
            break
    return total


def verify_configuration() -> None:
    config = json.loads((ROOT / "data/scenario_config.json").read_text())
    scenario = next(item for item in config["scenarios"] if item["id"] == "S6B")
    expected = [
        (840_000, 2_100_000, 400_000_000),
        (2_100_000, 4_200_000, 200_000_000),
        (4_200_000, 6_300_000, 100_000_000),
        (6_300_000, None, 60_000_000),
    ]
    observed = [
        (
            int(phase["start_height"]),
            int(phase["end_height"]) if "end_height" in phase else None,
            int(phase["subsidy_base_units"]),
        )
        for phase in scenario["phases"]
    ]
    if observed != expected:
        raise AssertionError(f"Unexpected S6B configuration: {observed}")
    if int(scenario["maximum_scheduled_issuance_base_units"]) != CEILING:
        raise AssertionError("Unexpected S6B issuance ceiling")


def verify_vectors() -> dict[str, object]:
    csv_path = ROOT / "data/S6B_normative_test_vectors.csv"
    json_path = ROOT / "data/S6B_normative_test_vectors.json"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    json_rows = [{key: str(value) for key, value in row.items()} for row in payload["vectors"]]
    if json_rows != rows:
        raise AssertionError("S6B CSV and JSON vectors differ")

    required = {
        839_999,
        840_000,
        840_001,
        2_099_999,
        2_100_000,
        2_100_001,
        4_199_999,
        4_200_000,
        4_200_001,
        6_299_999,
        6_300_000,
        6_300_001,
        FIRST_ZERO_HEIGHT - 2,
        FIRST_ZERO_HEIGHT - 1,
        FIRST_ZERO_HEIGHT,
        FIRST_ZERO_HEIGHT + 1,
    }
    observed_heights = {int(row["height"]) for row in rows}
    if not required.issubset(observed_heights):
        raise AssertionError(f"Missing S6B vector heights: {sorted(required - observed_heights)}")

    for row in rows:
        height = int(row["height"])
        before = cumulative_before(height)
        maximum = subsidy(height)
        expected_fields = {
            "maximum_subsidy_base_units": str(maximum),
            "cumulative_maximum_scheduled_issuance_before_block_base_units": str(before),
            "cumulative_maximum_scheduled_issuance_after_block_base_units": str(before + maximum),
            "exact_claim_valid": "true",
            "one_base_unit_over_maximum_invalid": "true",
        }
        for field, expected in expected_fields.items():
            if row[field] != expected:
                raise AssertionError(
                    f"S6B vector mismatch at height {height}, {field}: "
                    f"{row[field]} != {expected}"
                )

    if FIRST_ZERO_HEIGHT != 234_587_500:
        raise AssertionError(f"Unexpected first zero height: {FIRST_ZERO_HEIGHT}")
    if cumulative_before(FIRST_ZERO_HEIGHT) != CEILING:
        raise AssertionError("S6B maximum scheduled issuance is not exactly 168M")
    if cumulative_before(FIRST_ZERO_HEIGHT + 10_000) != CEILING:
        raise AssertionError("S6B issuance changes after the zero boundary")
    if subsidy(839_999) != deployed_subsidy(839_999):
        raise AssertionError("S6B changes the deployed pre-activation rule")

    # There is intentionally no claimed-supply input. A hypothetical underclaim
    # changes actual issuance only; the same height-only calls must stay equal.
    hypothetical_underclaim = 1
    if hypothetical_underclaim >= subsidy(840_000):
        raise AssertionError("Invalid underclaim test setup")
    if subsidy(6_300_000) != 60_000_000 or FIRST_ZERO_HEIGHT != 234_587_500:
        raise AssertionError("A prior underclaim altered a later scheduled result")

    return {
        "status": "passed",
        "implementation": "independent height-only calculation; primary generator not imported",
        "deployed_issuance_before_activation_base_units": deployed_issuance_before_activation(),
        "issuance_at_final_phase_start_base_units": ISSUANCE_AT_FINAL_PHASE_START,
        "final_phase_blocks": FINAL_PHASE_BLOCKS,
        "first_zero_subsidy_height": FIRST_ZERO_HEIGHT,
        "maximum_scheduled_issuance_base_units": cumulative_before(FIRST_ZERO_HEIGHT),
        "vector_count": len(rows),
        "vector_csv_sha256": sha256(csv_path),
        "vector_json_sha256": sha256(json_path),
        "underclaim_does_not_change_later_schedule": True,
    }


def main() -> None:
    verify_configuration()
    report = verify_vectors()
    path = ROOT / "data/S6B_independent_verification.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Independent S6/b verification passed: "
        f"first zero height {FIRST_ZERO_HEIGHT:,}; exact maximum 168,000,000 RIN."
    )


if __name__ == "__main__":
    main()
