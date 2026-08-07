#!/usr/bin/env python3
"""
Generate the stable Rincoin monetary-scenario review artifacts.

The JSON configuration is the source of truth. Consensus-deterministic schedules
are modeled as maximum permitted block subsidy = f(block_height). The schedule
builder does not use actual minted outputs, circulating supply, spendable supply,
UTXO state, burned coins, lost coins, dormant coins, fees, or underclaimed subsidy.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import textwrap
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


getcontext().prec = 80


@dataclass(frozen=True)
class Segment:
    scenario_id: str
    start_height: int
    end_height: int
    subsidy_base_units: int
    rule: str
    perpetual: bool = False

    @property
    def blocks(self) -> int:
        return self.end_height - self.start_height

    @property
    def scheduled_issuance_base_units(self) -> int:
        return self.blocks * self.subsidy_base_units


REVISION = ""


def load_config(root: Path) -> dict:
    with (root / "data" / f"{REVISION}scenario_config.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def rin(base_units: int, coin: int) -> Decimal:
    return Decimal(base_units) / Decimal(coin)


def fmt_decimal(value: Decimal, places: int = 8) -> str:
    quant = Decimal(1).scaleb(-places)
    return f"{value.quantize(quant):f}"


def scenario_display_id(scenario: dict) -> str:
    return scenario.get("display_id", scenario["id"])


def scenario_label(scenario: dict) -> str:
    return f"{scenario_display_id(scenario)} - {scenario['name']}"


def pct(part: int | Decimal, total: int | Decimal) -> Decimal:
    if total == 0:
        return Decimal(0)
    return Decimal(part) * Decimal(100) / Decimal(total)


def legacy_subsidy(height: int, initial_subsidy: int, epoch_blocks: int) -> int:
    halvings = height // epoch_blocks
    if halvings >= 64:
        return 0
    return initial_subsidy >> halvings


def plot_end_height(config: dict) -> int:
    net = config["network"]
    plot = config["plot"]
    return int(net["activation_height"]) + int(plot["years_after_activation"]) * int(net["blocks_per_year"])


def plot_end_height_for_years(config: dict, years_after_activation: int) -> int:
    net = config["network"]
    return int(net["activation_height"]) + int(years_after_activation) * int(net["blocks_per_year"])


def pre_activation_segments(config: dict, scenario_id: str) -> list[Segment]:
    net = config["network"]
    activation_height = int(net["activation_height"])
    epoch_blocks = int(net["epoch_blocks"])
    initial_subsidy = int(net["initial_subsidy_base_units"])

    segments: list[Segment] = []
    height = 0
    while height < activation_height:
        end_height = min(activation_height, ((height // epoch_blocks) + 1) * epoch_blocks)
        subsidy = legacy_subsidy(height, initial_subsidy, epoch_blocks)
        segments.append(Segment(scenario_id, height, end_height, subsidy, "legacy pre-activation binary halving"))
        height = end_height
    return segments


def total_scheduled(segments: Iterable[Segment]) -> int:
    return sum(segment.scheduled_issuance_base_units for segment in segments)


def build_legacy(config: dict, scenario: dict) -> list[Segment]:
    net = config["network"]
    epoch_blocks = int(net["epoch_blocks"])
    initial_subsidy = int(net["initial_subsidy_base_units"])
    scenario_id = scenario["id"]
    segments: list[Segment] = []
    height = 0
    while True:
        subsidy = legacy_subsidy(height, initial_subsidy, epoch_blocks)
        if subsidy == 0:
            break
        segments.append(Segment(scenario_id, height, height + epoch_blocks, subsidy, "deployed binary halving"))
        height += epoch_blocks
    return segments


def build_one_twentieth_no_floor(config: dict, scenario: dict) -> list[Segment]:
    net = config["network"]
    epoch_blocks = int(net["epoch_blocks"])
    activation_height = int(net["activation_height"])
    scenario_id = scenario["id"]
    numerator = int(scenario["reduction_numerator"])
    denominator = int(scenario["reduction_denominator"])
    segments = pre_activation_segments(config, scenario_id)

    previous_subsidy = segments[-1].subsidy_base_units
    height = activation_height
    while True:
        subsidy = previous_subsidy * numerator // denominator
        if subsidy == 0:
            break
        segments.append(Segment(scenario_id, height, height + epoch_blocks, subsidy, "1/20 epoch reduction"))
        previous_subsidy = subsidy
        height += epoch_blocks
    return segments


def build_extended_epoch_binary_halving(config: dict, scenario: dict) -> list[Segment]:
    net = config["network"]
    activation_height = int(net["activation_height"])
    legacy_epoch_blocks = int(net["epoch_blocks"])
    initial_subsidy = int(net["initial_subsidy_base_units"])
    scenario_id = scenario["id"]
    epoch_anchor_height = int(scenario["epoch_anchor_height"])
    post_activation_epoch_blocks = int(scenario["post_activation_epoch_blocks"])
    segments = pre_activation_segments(config, scenario_id)

    if epoch_anchor_height > activation_height:
        raise ValueError(
            f"{scenario_id} epoch anchor must not be after activation height"
        )
    if epoch_anchor_height % legacy_epoch_blocks != 0:
        raise ValueError(
            f"{scenario_id} epoch anchor must align with a deployed reward boundary"
        )

    elapsed_extended_epochs = (
        activation_height - epoch_anchor_height
    ) // post_activation_epoch_blocks
    current_epoch_end = epoch_anchor_height + (
        elapsed_extended_epochs + 1
    ) * post_activation_epoch_blocks
    subsidy = legacy_subsidy(
        epoch_anchor_height,
        initial_subsidy,
        legacy_epoch_blocks,
    )
    subsidy >>= elapsed_extended_epochs

    if subsidy > 0 and activation_height < current_epoch_end:
        segments.append(
            Segment(
                scenario_id,
                activation_height,
                current_epoch_end,
                subsidy,
                (
                    f"extended {post_activation_epoch_blocks}-block binary "
                    f"halving epoch anchored at {epoch_anchor_height}"
                ),
            )
        )

    height = current_epoch_end
    while True:
        subsidy //= 2
        if subsidy == 0:
            break
        segments.append(
            Segment(
                scenario_id,
                height,
                height + post_activation_epoch_blocks,
                subsidy,
                f"extended {post_activation_epoch_blocks}-block binary halving epoch",
            )
        )
        height += post_activation_epoch_blocks
    return segments


def build_one_twentieth_finite_floor(config: dict, scenario: dict) -> list[Segment]:
    net = config["network"]
    epoch_blocks = int(net["epoch_blocks"])
    activation_height = int(net["activation_height"])
    ceiling = int(net["maximum_supply_ceiling_base_units"])
    floor_subsidy = int(scenario["floor_subsidy_base_units"])
    scenario_id = scenario["id"]
    segments = pre_activation_segments(config, scenario_id)

    previous_subsidy = segments[-1].subsidy_base_units
    height = activation_height
    while True:
        candidate = previous_subsidy * 19 // 20
        if candidate < floor_subsidy:
            break
        segments.append(Segment(scenario_id, height, height + epoch_blocks, candidate, "1/20 epoch reduction"))
        previous_subsidy = candidate
        height += epoch_blocks

    remaining = max(0, ceiling - total_scheduled(segments))
    floor_blocks = remaining // floor_subsidy
    if floor_blocks:
        segments.append(
            Segment(
                scenario_id,
                height,
                height + floor_blocks,
                floor_subsidy,
                f"finite predetermined {fmt_decimal(rin(floor_subsidy, int(net['coin_unit_base_units'])))} RIN constant phase",
            )
        )
    return segments


def build_cap_derived_113_114(config: dict, scenario: dict) -> list[Segment]:
    net = config["network"]
    epoch_blocks = int(net["epoch_blocks"])
    activation_height = int(net["activation_height"])
    scenario_id = scenario["id"]
    segments = pre_activation_segments(config, scenario_id)

    previous_subsidy = segments[-1].subsidy_base_units
    height = activation_height
    while True:
        subsidy = previous_subsidy * 113 // 114
        if subsidy == 0:
            break
        segments.append(Segment(scenario_id, height, height + epoch_blocks, subsidy, "idealized 113/114 comparator"))
        previous_subsidy = subsidy
        height += epoch_blocks
    return segments


def build_configured_phases(config: dict, scenario: dict) -> list[Segment]:
    scenario_id = scenario["id"]
    segments: list[Segment] = []
    for phase in scenario["phases"]:
        perpetual = bool(phase.get("perpetual", False))
        end_height = plot_end_height(config) if perpetual else int(phase["end_height"])
        segments.append(
            Segment(
                scenario_id,
                int(phase["start_height"]),
                end_height,
                int(phase["subsidy_base_units"]),
                phase["rule"],
                perpetual=perpetual,
            )
        )
    return segments


def build_bounded_height_phases_to_ceiling(
    config: dict, scenario: dict
) -> list[Segment]:
    """Build a height-only schedule whose final phase ends at an exact ceiling.

    Historical issuance is derived from the deployed pre-activation rule. The
    final height is not accepted as configuration input: it is calculated from
    the remaining integer base units and the final phase subsidy.
    """

    net = config["network"]
    scenario_id = scenario["id"]
    activation = int(net["activation_height"])
    ceiling = int(scenario["maximum_scheduled_issuance_base_units"])
    if ceiling != int(net["maximum_supply_ceiling_base_units"]):
        raise ValueError(f"{scenario_id} ceiling must equal the declared 168M ceiling")

    segments = pre_activation_segments(config, scenario_id)
    phases = scenario["phases"]
    if not phases or int(phases[0]["start_height"]) != activation:
        raise ValueError(f"{scenario_id} phases must begin at activation")

    expected_start = activation
    for index, phase in enumerate(phases):
        start = int(phase["start_height"])
        if start != expected_start:
            raise ValueError(f"{scenario_id} phase {index} is not contiguous")
        subsidy = int(phase["subsidy_base_units"])
        if subsidy <= 0:
            raise ValueError(f"{scenario_id} phase {index} subsidy must be positive")

        is_final = index == len(phases) - 1
        if not is_final:
            end = int(phase["end_height"])
            if end <= start:
                raise ValueError(f"{scenario_id} phase {index} has an invalid end")
        else:
            if "end_height" in phase:
                raise ValueError(
                    f"{scenario_id} final height must be derived, not configured"
                )
            issued_before_final = total_scheduled(segments)
            remaining = ceiling - issued_before_final
            if remaining <= 0 or remaining % subsidy:
                raise ValueError(
                    f"{scenario_id} ceiling is not exactly reachable by its final phase"
                )
            end = start + remaining // subsidy

        segments.append(
            Segment(scenario_id, start, end, subsidy, str(phase["rule"]))
        )
        expected_start = end

    if total_scheduled(segments) != ceiling:
        raise AssertionError(f"{scenario_id} does not reach its exact ceiling")
    return segments


def build_one_twentieth_perpetual_floor(config: dict, scenario: dict) -> list[Segment]:
    net = config["network"]
    epoch_blocks = int(net["epoch_blocks"])
    activation_height = int(net["activation_height"])
    floor_subsidy = int(scenario["floor_subsidy_base_units"])
    scenario_id = scenario["id"]
    segments = pre_activation_segments(config, scenario_id)

    previous_subsidy = segments[-1].subsidy_base_units
    height = activation_height
    end = plot_end_height(config)
    while height < end:
        candidate = previous_subsidy * 19 // 20
        if candidate < floor_subsidy:
            break
        segments.append(Segment(scenario_id, height, height + epoch_blocks, candidate, "1/20 epoch reduction"))
        previous_subsidy = candidate
        height += epoch_blocks

    if height < end:
        segments.append(Segment(scenario_id, height, end, floor_subsidy, "perpetual tail comparator", perpetual=True))
    return segments


def build_segments(config: dict, scenario: dict) -> list[Segment]:
    kind = scenario["kind"]
    if kind == "legacy_binary":
        return build_legacy(config, scenario)
    if kind == "one_twentieth_no_floor":
        return build_one_twentieth_no_floor(config, scenario)
    if kind == "extended_epoch_binary_halving":
        return build_extended_epoch_binary_halving(config, scenario)
    if kind == "one_twentieth_finite_floor":
        return build_one_twentieth_finite_floor(config, scenario)
    if kind == "cap_derived_113_114":
        return build_cap_derived_113_114(config, scenario)
    if kind == "configured_phases":
        return build_configured_phases(config, scenario)
    if kind == "bounded_height_phases_to_ceiling":
        return build_bounded_height_phases_to_ceiling(config, scenario)
    if kind == "one_twentieth_perpetual_floor":
        return build_one_twentieth_perpetual_floor(config, scenario)
    raise ValueError(f"Unknown scenario kind: {kind}")


def scheduled_before(segments: list[Segment], height: int) -> int:
    total = 0
    for segment in segments:
        if segment.perpetual and height > segment.start_height:
            covered = height - segment.start_height
            total += covered * segment.subsidy_base_units
            break
        if height <= segment.start_height:
            break
        covered = min(height, segment.end_height) - segment.start_height
        if covered > 0:
            total += covered * segment.subsidy_base_units
        if height < segment.end_height:
            break
    return total


def subsidy_at(segments: list[Segment], height: int) -> int:
    for segment in segments:
        if segment.perpetual and height >= segment.start_height:
            return segment.subsidy_base_units
        if segment.start_height <= height < segment.end_height:
            return segment.subsidy_base_units
    return 0


def issuance_between(segments: list[Segment], start_height: int, end_height: int) -> int:
    return scheduled_before(segments, end_height) - scheduled_before(segments, start_height)


def first_height_below(segments: list[Segment], threshold_base_units: int) -> int | None:
    for segment in segments:
        if segment.subsidy_base_units < threshold_base_units:
            return segment.start_height
    if segments and not any(segment.perpetual for segment in segments) and threshold_base_units > 0:
        return segments[-1].end_height
    return None


def first_zero_height(segments: list[Segment]) -> int | None:
    if segments and not any(segment.perpetual for segment in segments):
        return segments[-1].end_height
    return None


def constant_phase(segments: list[Segment]) -> Segment | None:
    for segment in segments:
        if "constant phase" in segment.rule or "perpetual" in segment.rule:
            return segment
    return None


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def export_segments(root: Path, config: dict, scenario: dict, segments: list[Segment]) -> None:
    coin = int(config["network"]["coin_unit_base_units"])
    rows = []
    cumulative = 0
    for segment in segments:
        issuance = segment.scheduled_issuance_base_units
        cumulative += issuance
        rows.append(
            {
                "scenario_id": scenario["id"],
                "scenario_display_id": scenario_display_id(scenario),
                "scenario_name": scenario["name"],
                "start_height": segment.start_height,
                "end_height": segment.end_height,
                "blocks": segment.blocks,
                "maximum_permitted_subsidy_base_units": segment.subsidy_base_units,
                "maximum_permitted_subsidy_rin_display": fmt_decimal(rin(segment.subsidy_base_units, coin)),
                "scheduled_issuance_base_units": issuance,
                "scheduled_issuance_rin_display": fmt_decimal(rin(issuance, coin)),
                "cumulative_scheduled_issuance_base_units": cumulative,
                "cumulative_scheduled_issuance_rin_display": fmt_decimal(rin(cumulative, coin)),
                "perpetual_or_truncated": str(segment.perpetual).lower(),
                "rule": segment.rule,
            }
        )
    write_csv(root / "data" / f"{REVISION}{scenario['id']}_segments.csv", rows)


def remove_stale_segment_exports(root: Path, scenarios: list[dict]) -> None:
    expected = {f"{REVISION}{scenario['id']}_segments.csv" for scenario in scenarios}
    for path in (root / "data").glob(f"{REVISION}S*_segments.csv"):
        if path.name not in expected:
            path.unlink()


def remove_stale_candidate_exports(root: Path) -> None:
    for relative in (
        "data/s1_normative_test_vectors.csv",
        "data/s1_normative_test_vectors.json",
        "data/s1_normative_test_vectors.sha256",
        "includes/s1_normative_vectors_table.qmd",
        "includes/s1_vector_hashes_table.qmd",
    ):
        path = root / relative
        if path.exists():
            path.unlink()


def scenario_summary(config: dict, scenarios: list[dict], built: dict[str, list[Segment]]) -> list[dict]:
    net = config["network"]
    coin = int(net["coin_unit_base_units"])
    ceiling = int(net["maximum_supply_ceiling_base_units"])
    activation = int(net["activation_height"])
    blocks_per_year = int(net["blocks_per_year"])
    s0_total = total_scheduled(built["S0"])
    rows = []
    for scenario in scenarios:
        segments = built[scenario["id"]]
        unbounded = any(segment.perpetual for segment in segments)
        total = total_scheduled(segments)
        phase = constant_phase(segments)
        fixed_issuance = phase.scheduled_issuance_base_units if phase and not phase.perpetual else ""
        final_total = "" if unbounded else total
        post_activation = "" if unbounded else max(0, total - scheduled_before(segments, activation))
        fixed_share_final = ""
        fixed_share_post = ""
        if phase and not phase.perpetual and total:
            fixed_share_final = fmt_decimal(pct(phase.scheduled_issuance_base_units, total))
            post = total - scheduled_before(segments, activation)
            fixed_share_post = fmt_decimal(pct(phase.scheduled_issuance_base_units, post))
        rows.append(
            {
                "scenario_id": scenario["id"],
                "scenario_display_id": scenario_display_id(scenario),
                "scenario_name": scenario["name"],
                "kind": scenario["kind"],
                "activation_height": activation,
                "supply_at_activation_base_units": scheduled_before(segments, activation),
                "supply_at_activation_rin_display": fmt_decimal(rin(scheduled_before(segments, activation), coin)),
                "first_activation_subsidy_base_units": subsidy_at(segments, activation),
                "first_activation_subsidy_rin_display": fmt_decimal(rin(subsidy_at(segments, activation), coin)),
                "first_height_below_1_rin": first_height_below(segments, coin) or "",
                "first_height_below_0_5_rin": first_height_below(segments, coin // 2) or "",
                "constant_phase_start_height": phase.start_height if phase else "",
                "constant_phase_end_height": "" if not phase or phase.perpetual else phase.end_height,
                "constant_phase_subsidy_base_units": phase.subsidy_base_units if phase else "",
                "constant_phase_subsidy_rin_display": fmt_decimal(rin(phase.subsidy_base_units, coin)) if phase else "",
                "constant_phase_blocks": "" if not phase or phase.perpetual else phase.blocks,
                "constant_phase_years": "" if not phase or phase.perpetual else fmt_decimal(Decimal(phase.blocks) / Decimal(blocks_per_year)),
                "constant_phase_issuance_base_units": fixed_issuance,
                "constant_phase_issuance_rin_display": fmt_decimal(rin(fixed_issuance, coin)) if fixed_issuance != "" else "",
                "constant_phase_share_of_final_scheduled_issuance": fixed_share_final,
                "constant_phase_share_of_post_activation_issuance": fixed_share_post,
                "first_zero_subsidy_height": first_zero_height(segments) or "",
                "maximum_scheduled_issuance_base_units": final_total,
                "maximum_scheduled_issuance_rin_display": fmt_decimal(rin(final_total, coin)) if final_total != "" else "",
                "maximum_supply_ceiling_base_units": ceiling,
                "maximum_supply_ceiling_rin_display": fmt_decimal(rin(ceiling, coin)),
                "undershoot_base_units": ceiling - total if not unbounded else "",
                "undershoot_rin_display": fmt_decimal(rin(ceiling - total, coin)) if not unbounded else "",
                "post_activation_issuance_base_units": post_activation,
                "post_activation_issuance_rin_display": fmt_decimal(rin(post_activation, coin)) if post_activation != "" else "",
                "ceiling_usage_percent": fmt_decimal(pct(total, ceiling)) if not unbounded else "",
                "supply_multiple_relative_to_s0": fmt_decimal(Decimal(total) / Decimal(s0_total)) if not unbounded else "",
                "scheduled_issuance_through_plot_end_base_units": total,
                "scheduled_issuance_through_plot_end_rin_display": fmt_decimal(rin(total, coin)),
                "unbounded": str(unbounded).lower(),
            }
        )
    return rows


def export_horizon_table(root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]) -> None:
    net = config["network"]
    coin = int(net["coin_unit_base_units"])
    activation = int(net["activation_height"])
    blocks_per_year = int(net["blocks_per_year"])
    ceiling = int(net["maximum_supply_ceiling_base_units"])

    base_horizons = []
    for item in config["horizons"]:
        if "height" in item:
            height = int(item["height"])
            years = Decimal(height - activation) / Decimal(blocks_per_year)
        else:
            years = Decimal(str(item["years_after_activation"]))
            height = activation + int(years * blocks_per_year)
        base_horizons.append((item["label"], years, height))

    rows = []
    seen = set()
    for scenario in scenarios:
        segments = built[scenario["id"]]
        scenario_horizons = list(base_horizons)
        phase = constant_phase(segments)
        if phase:
            scenario_horizons.append(("constant phase start", Decimal(phase.start_height - activation) / Decimal(blocks_per_year), phase.start_height))
            if not phase.perpetual:
                scenario_horizons.append(("constant phase end", Decimal(phase.end_height - activation) / Decimal(blocks_per_year), phase.end_height))
        zero = first_zero_height(segments)
        if zero is not None:
            scenario_horizons.append(("terminal height", Decimal(zero - activation) / Decimal(blocks_per_year), zero))
        for label, years, height in scenario_horizons:
            key = (scenario["id"], label, height)
            if key in seen:
                continue
            seen.add(key)
            annual = issuance_between(segments, height, height + blocks_per_year)
            cumulative = scheduled_before(segments, height)
            unbounded = any(segment.perpetual for segment in segments)
            remaining = "" if unbounded else max(0, total_scheduled(segments) - cumulative)
            rows.append(
                {
                    "scenario_id": scenario["id"],
                    "scenario_display_id": scenario_display_id(scenario),
                    "scenario_name": scenario["name"],
                    "horizon_label": label,
                    "horizon_years_after_activation": fmt_decimal(years),
                    "height": height,
                    "subsidy_base_units": subsidy_at(segments, height),
                    "subsidy_rin_display": fmt_decimal(rin(subsidy_at(segments, height), coin)),
                    "next_year_issuance_base_units": annual,
                    "next_year_issuance_rin_display": fmt_decimal(rin(annual, coin)),
                    "next_year_issuance_pct_of_scheduled_supply": fmt_decimal(pct(annual, cumulative)),
                    "scheduled_issuance_before_height_base_units": cumulative,
                    "scheduled_issuance_before_height_rin_display": fmt_decimal(rin(cumulative, coin)),
                    "remaining_scheduled_issuance_base_units": remaining,
                    "remaining_scheduled_issuance_rin_display": fmt_decimal(rin(remaining, coin)) if remaining != "" else "",
                    "maximum_supply_ceiling_remaining_base_units": max(0, ceiling - cumulative),
                    "maximum_supply_ceiling_remaining_rin_display": fmt_decimal(rin(max(0, ceiling - cumulative), coin)),
                }
            )
    write_csv(root / "data" / f"{REVISION}horizon_table.csv", rows)


def export_boundary_vectors(root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]) -> None:
    coin = int(config["network"]["coin_unit_base_units"])
    rows = []
    for scenario in scenarios:
        segments = built[scenario["id"]]
        heights = set()
        for segment in segments:
            if segment.start_height >= 0:
                heights.update({segment.start_height - 1, segment.start_height, segment.start_height + 1})
            if not segment.perpetual:
                heights.update({segment.end_height - 1, segment.end_height, segment.end_height + 1})
        for height in sorted(h for h in heights if h >= 0):
            rows.append(
                {
                    "scenario_id": scenario["id"],
                    "scenario_display_id": scenario_display_id(scenario),
                    "scenario_name": scenario["name"],
                    "height": height,
                    "subsidy_base_units": subsidy_at(segments, height),
                    "subsidy_rin_display": fmt_decimal(rin(subsidy_at(segments, height), coin)),
                    "scheduled_issuance_before_height_base_units": scheduled_before(segments, height),
                    "scheduled_issuance_before_height_rin_display": fmt_decimal(rin(scheduled_before(segments, height), coin)),
                    "note": "boundary probe",
                }
            )
    write_csv(root / "data" / f"{REVISION}boundary_vectors.csv", rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_s1_normative_vectors(
    root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]
) -> None:
    net = config["network"]
    coin = int(net["coin_unit_base_units"])
    activation = int(net["activation_height"])
    epoch_blocks = int(net["epoch_blocks"])
    s1 = next(scenario for scenario in scenarios if scenario["id"] == "S1")
    segments = built["S1"]

    height_classes: dict[int, set[str]] = {}

    def add(height: int, label: str) -> None:
        if height >= 0:
            height_classes.setdefault(height, set()).add(label)

    add(activation - 1, "last pre-activation block")
    add(activation, "activation block")
    add(activation + 1, "second activation-epoch block")

    for epoch_index in range(1, 11):
        start = activation + (epoch_index - 1) * epoch_blocks
        end = start + epoch_blocks
        add(start, f"first block of post-activation epoch {epoch_index}")
        add(end - 1, f"last block of post-activation epoch {epoch_index}")

    for label, threshold in (
        ("crossing below 1 RIN", coin),
        ("crossing below 0.5 RIN", coin // 2),
        ("crossing below 0.1 RIN", coin // 10),
    ):
        crossing = first_height_below(segments, threshold)
        if crossing is None:
            raise ValueError(f"S1 has no {label}")
        add(crossing - 1, f"last block before {label}")
        add(crossing, label)
        add(crossing + 1, f"second block after {label}")

    final_segment = segments[-1]
    zero_height = first_zero_height(segments)
    if zero_height is None:
        raise ValueError("S1 must have a first zero-subsidy height")
    add(final_segment.start_height, "first one-base-unit subsidy block")
    add(final_segment.end_height - 1, "final non-zero subsidy block")
    add(zero_height, "first zero-subsidy block")
    add(zero_height + 1, "second zero-subsidy block")

    rows: list[dict[str, str | int]] = []
    for number, height in enumerate(sorted(height_classes), 1):
        if height < activation:
            epoch_index: str | int = "legacy"
            recurrence_input: str | int = ""
        else:
            epoch_index = ((height - activation) // epoch_blocks) + 1
            epoch_start = activation + (int(epoch_index) - 1) * epoch_blocks
            recurrence_input = subsidy_at(segments, epoch_start - 1)
        rows.append(
            {
                "vector_id": f"S1-{number:03d}",
                "height": height,
                "post_activation_epoch_index": epoch_index,
                "recurrence_input_subsidy_base_units": recurrence_input,
                "maximum_permitted_subsidy_base_units": subsidy_at(segments, height),
                "maximum_permitted_subsidy_rin": fmt_decimal(
                    rin(subsidy_at(segments, height), coin)
                ),
                "scheduled_issuance_before_height_base_units": scheduled_before(
                    segments, height
                ),
                "expected_rule": (
                    "deployed pre-activation rule"
                    if height < activation
                    else (
                        "zero after integer exhaustion"
                        if subsidy_at(segments, height) == 0
                        else (
                            f"floor(previous_epoch_subsidy * "
                            f"{s1['reduction_numerator']} / "
                            f"{s1['reduction_denominator']})"
                        )
                    )
                ),
                "notes": "; ".join(sorted(height_classes[height])),
            }
        )

    csv_path = root / "data" / "S1_normative_test_vectors.csv"
    json_path = root / "data" / "S1_normative_test_vectors.json"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "document_version": config["metadata"]["document_version"],
                "publication_date": config["metadata"]["publication_date"],
                "scenario": "S1",
                "consensus_rule": {
                    "activation_height": activation,
                    "epoch_blocks": epoch_blocks,
                    "coin_base_units": coin,
                    "reduction_numerator": int(s1["reduction_numerator"]),
                    "reduction_denominator": int(s1["reduction_denominator"]),
                    "recurrence": s1["recurrence"],
                    "rounding": s1["rounding"],
                    "first_zero_subsidy_height": zero_height,
                },
                "vectors": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    hash_path = root / "data" / "S1_normative_test_vectors.sha256"
    hash_path.write_text(
        f"{sha256(csv_path)}  data/{csv_path.name}\n"
        f"{sha256(json_path)}  data/{json_path.name}\n",
        encoding="utf-8",
    )


def export_s5b_normative_vectors(
    root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]
) -> None:
    net = config["network"]
    coin = int(net["coin_unit_base_units"])
    activation = int(net["activation_height"])
    scenario = next(item for item in scenarios if item["id"] == "S5B")
    anchor = int(scenario["epoch_anchor_height"])
    epoch_blocks = int(scenario["post_activation_epoch_blocks"])
    base_subsidy = legacy_subsidy(
        anchor,
        int(net["initial_subsidy_base_units"]),
        int(net["epoch_blocks"]),
    )
    segments = built["S5B"]

    height_classes: dict[int, set[str]] = {}

    def add(height: int, label: str) -> None:
        if height >= 0:
            height_classes.setdefault(height, set()).add(label)

    add(activation - 1, "last pre-activation block")
    add(activation, "activation block; phase index 0")
    add(activation + 1, "second activation-phase block")

    for phase_index in range(1, 11):
        start = anchor + phase_index * epoch_blocks
        add(start - 1, f"last block of long phase {phase_index - 1}")
        add(start, f"first block of long phase {phase_index}")
        add(start + 1, f"second block of long phase {phase_index}")

    for label, threshold in (
        ("crossing below 1 RIN", coin),
        ("crossing below 0.5 RIN", coin // 2),
        ("crossing below 0.1 RIN", coin // 10),
    ):
        crossing = first_height_below(segments, threshold)
        if crossing is None:
            raise ValueError(f"S5B has no {label}")
        add(crossing - 1, f"last block before {label}")
        add(crossing, label)
        add(crossing + 1, f"second block after {label}")

    final_segment = segments[-1]
    zero_height = first_zero_height(segments)
    if zero_height is None:
        raise ValueError("S5B must have a first zero-subsidy height")
    add(final_segment.start_height, "first one-base-unit subsidy block")
    add(final_segment.end_height - 1, "final non-zero subsidy block")
    add(zero_height, "first zero-subsidy block")
    add(zero_height + 1, "second zero-subsidy block")

    rows: list[dict[str, str | int]] = []
    for number, height in enumerate(sorted(height_classes), 1):
        if height < activation:
            phase_index: str | int = "legacy"
            calculation = "deployed pre-activation rule"
        else:
            phase_index = (height - anchor) // epoch_blocks
            calculation = (
                "zero after integer exhaustion"
                if subsidy_at(segments, height) == 0
                else f"{base_subsidy} >> {phase_index}"
            )
        rows.append(
            {
                "vector_id": f"S5B-{number:03d}",
                "height": height,
                "long_epoch_index": phase_index,
                "phase_anchor_height": anchor if height >= activation else "",
                "maximum_permitted_subsidy_base_units": subsidy_at(
                    segments, height
                ),
                "maximum_permitted_subsidy_rin": fmt_decimal(
                    rin(subsidy_at(segments, height), coin)
                ),
                "scheduled_issuance_before_height_base_units": scheduled_before(
                    segments, height
                ),
                "expected_rule": calculation,
                "notes": "; ".join(sorted(height_classes[height])),
            }
        )

    csv_path = root / "data" / "S5B_normative_test_vectors.csv"
    json_path = root / "data" / "S5B_normative_test_vectors.json"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "document_version": config["metadata"]["document_version"],
                "publication_date": config["metadata"]["publication_date"],
                "scenario": "S5B",
                "scenario_display_id": "S5/b",
                "consensus_rule": {
                    "activation_height": activation,
                    "phase_anchor_height": anchor,
                    "long_epoch_blocks": epoch_blocks,
                    "coin_base_units": coin,
                    "base_subsidy_base_units": base_subsidy,
                    "calculation": (
                        "for h >= activation, n = floor((h - phase_anchor) / "
                        "long_epoch_blocks); subsidy = base_subsidy >> n"
                    ),
                    "first_zero_subsidy_height": zero_height,
                },
                "vectors": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    hash_path = root / "data" / "S5B_normative_test_vectors.sha256"
    hash_path.write_text(
        f"{sha256(csv_path)}  data/{csv_path.name}\n"
        f"{sha256(json_path)}  data/{json_path.name}\n",
        encoding="utf-8",
    )


def export_s6b_normative_vectors(
    root: Path,
    config: dict,
    scenarios: list[dict],
    built: dict[str, list[Segment]],
) -> None:
    net = config["network"]
    coin = int(net["coin_unit_base_units"])
    activation = int(net["activation_height"])
    ceiling = int(net["maximum_supply_ceiling_base_units"])
    scenario = next(item for item in scenarios if item["id"] == "S6B")
    segments = built["S6B"]
    zero_height = first_zero_height(segments)
    if zero_height is None:
        raise ValueError("S6B must have a deterministic zero-subsidy height")

    height_classes: dict[int, set[str]] = {}

    def add(height: int, label: str) -> None:
        if height >= 0:
            height_classes.setdefault(height, set()).add(label)

    for height, label in (
        (activation - 1, "last pre-activation block"),
        (activation, "activation block"),
        (activation + 1, "second activation-phase block"),
        (2_099_999, "final 4 RIN block"),
        (2_100_000, "first 2 RIN block"),
        (2_100_001, "second 2 RIN block"),
        (4_199_999, "final 2 RIN block"),
        (4_200_000, "first 1 RIN block"),
        (4_200_001, "second 1 RIN block"),
        (6_299_999, "final 1 RIN block"),
        (6_300_000, "first 0.6 RIN block"),
        (6_300_001, "second 0.6 RIN block"),
        (zero_height - 2, "penultimate non-zero block"),
        (zero_height - 1, "final non-zero block"),
        (zero_height, "first zero-subsidy block"),
        (zero_height + 1, "second zero-subsidy block"),
    ):
        add(height, label)

    def phase_identifier(height: int) -> str:
        if height < activation:
            return "deployed-pre-activation"
        if height < 2_100_000:
            return "S6B-4-RIN"
        if height < 4_200_000:
            return "S6B-2-RIN"
        if height < 6_300_000:
            return "S6B-1-RIN"
        if height < zero_height:
            return "S6B-0.6-RIN"
        return "S6B-zero"

    rows: list[dict[str, str | int]] = []
    for number, height in enumerate(sorted(height_classes), 1):
        maximum = subsidy_at(segments, height)
        before = scheduled_before(segments, height)
        after = before + maximum
        rows.append(
            {
                "vector_id": f"S6B-{number:03d}",
                "height": height,
                "phase_identifier": phase_identifier(height),
                "maximum_subsidy_base_units": maximum,
                "maximum_subsidy_rin": fmt_decimal(rin(maximum, coin)),
                "cumulative_maximum_scheduled_issuance_before_block_base_units": before,
                "cumulative_maximum_scheduled_issuance_before_block_rin": fmt_decimal(rin(before, coin)),
                "cumulative_maximum_scheduled_issuance_after_block_base_units": after,
                "cumulative_maximum_scheduled_issuance_after_block_rin": fmt_decimal(rin(after, coin)),
                "exact_claim_valid": "true",
                "one_base_unit_over_maximum_invalid": "true",
                "notes": "; ".join(sorted(height_classes[height])),
            }
        )

    if scheduled_before(segments, zero_height) != ceiling:
        raise AssertionError("S6B terminal issuance is not exactly 168M RIN")
    if scheduled_before(segments, zero_height + 1) != ceiling:
        raise AssertionError("S6B zero phase changes scheduled issuance")
    if subsidy_at(segments, activation - 1) != legacy_subsidy(
        activation - 1,
        int(net["initial_subsidy_base_units"]),
        int(net["epoch_blocks"]),
    ):
        raise AssertionError("S6B changes a pre-activation subsidy")

    csv_path = root / "data" / "S6B_normative_test_vectors.csv"
    json_path = root / "data" / "S6B_normative_test_vectors.json"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "document_version": config["metadata"]["document_version"],
                "publication_date": config["metadata"]["publication_date"],
                "scenario": "S6B",
                "scenario_display_id": "S6/b",
                "interpretation_status": (
                    "provisional bounded deterministic interpretation pending "
                    "clarification from the study author"
                ),
                "consensus_rule": {
                    "activation_height": activation,
                    "coin_base_units": coin,
                    "maximum_scheduled_issuance_base_units": ceiling,
                    "first_zero_subsidy_height": zero_height,
                    "terminal_height_derivation": (
                        "deployed issuance before 840000 plus configured finite "
                        "height phases; remaining ceiling divided exactly by "
                        "60000000 base units"
                    ),
                    "underclaim_semantics": (
                        "underclaimed subsidy is not reissued and does not change "
                        "any later height result or the terminal height"
                    ),
                    "stateful_supply_inputs": False,
                },
                "assertions": {
                    "pre_activation_rule_unchanged": True,
                    "maximum_scheduled_issuance_is_exactly_168m_rin": True,
                    "first_zero_subsidy_height_is_deterministic": True,
                    "underclaim_does_not_change_later_vectors": True,
                },
                "vectors": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    hash_path = root / "data" / "S6B_normative_test_vectors.sha256"
    hash_path.write_text(
        f"{sha256(csv_path)}  data/{csv_path.name}\n"
        f"{sha256(json_path)}  data/{json_path.name}\n",
        encoding="utf-8",
    )


def export_s1_half_life(root: Path, config: dict, scenarios: list[dict]) -> None:
    net = config["network"]
    s1 = next(scenario for scenario in scenarios if scenario["id"] == "S1")
    ratio = int(s1["reduction_numerator"]) / int(s1["reduction_denominator"])
    epochs = math.log(0.5) / math.log(ratio)
    years = epochs * int(net["epoch_blocks"]) / int(net["blocks_per_year"])
    write_csv(
        root / "data" / "s1_subsidy_half_life.csv",
        [
            {
                "scenario_id": "S1",
                "reduction_ratio": f"{ratio:.8f}",
                "mathematical_half_life_epochs": f"{epochs:.8f}",
                "mathematical_half_life_target_years": f"{years:.8f}",
                "metric_status": "descriptive real-number metric; consensus uses recursive integer arithmetic",
            }
        ],
    )

def export_s0_half_life(root: Path, config: dict, scenarios: list[dict]) -> None:
    net = config["network"]
    s0 = next(scenario for scenario in scenarios if scenario["id"] == "S0")
    ratio = int(s0["reduction_numerator"]) / int(s0["reduction_denominator"])
    epochs = math.log(0.5) / math.log(ratio)
    years = epochs * int(net["epoch_blocks"]) / int(net["blocks_per_year"])
    write_csv(
        root / "data" / "s0_subsidy_half_life.csv",
        [
            {
                "scenario_id": "S0",
                "reduction_ratio": f"{ratio:.8f}",
                "mathematical_half_life_epochs": f"{epochs:.8f}",
                "mathematical_half_life_target_years": f"{years:.8f}",
                "metric_status": "descriptive real-number metric; consensus uses recursive integer arithmetic",
            }
        ],
    )


def first_later_reduction(
    segments: list[Segment], activation_height: int
) -> tuple[int, int, int]:
    for segment in segments:
        if segment.start_height <= activation_height:
            continue
        before = subsidy_at(segments, segment.start_height - 1)
        after = subsidy_at(segments, segment.start_height)
        if after < before:
            return segment.start_height, before, after
    raise ValueError("Scenario has no later subsidy reduction")


def ten_year_expansion_points(value_pct: Decimal, two_point_upper: Decimal) -> int:
    if value_pct <= Decimal(25):
        return 4
    if value_pct <= Decimal(60):
        return 3
    if value_pct <= two_point_upper:
        return 2
    if value_pct <= Decimal(150):
        return 1
    return 0


def export_s1_s5b_comparison(
    root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]
) -> None:
    net = config["network"]
    activation = int(net["activation_height"])
    coin = int(net["coin_unit_base_units"])
    blocks_per_year = int(net["blocks_per_year"])
    scenario_map = {scenario["id"]: scenario for scenario in scenarios}
    legacy_activation_subsidy = subsidy_at(built["S0"], activation - 1)
    supply_at_activation = scheduled_before(built["S0"], activation)
    rows: list[dict[str, str | int]] = []

    candidate_parameters = {
        "S1": {
            "normal_reduction_pct": Decimal(5),
            "cadence_blocks": int(net["epoch_blocks"]),
            "half_life_epochs": Decimal(
                str(
                    math.log(0.5)
                    / math.log(
                        int(scenario_map["S1"]["reduction_numerator"])
                        / int(scenario_map["S1"]["reduction_denominator"])
                    )
                )
            ),
        },
        "S5B": {
            "normal_reduction_pct": Decimal(50),
            "cadence_blocks": int(
                scenario_map["S5B"]["post_activation_epoch_blocks"]
            ),
            "half_life_epochs": Decimal(1),
        },
    }

    for scenario_id in ("S1", "S5B"):
        scenario = scenario_map[scenario_id]
        segments = built[scenario_id]
        first_height, before, after = first_later_reduction(segments, activation)
        activation_subsidy = subsidy_at(segments, activation)
        immediate_shock = (
            Decimal(legacy_activation_subsidy - activation_subsidy)
            * Decimal(100)
            / Decimal(legacy_activation_subsidy)
        )
        cadence_blocks = candidate_parameters[scenario_id]["cadence_blocks"]
        half_life_epochs = candidate_parameters[scenario_id]["half_life_epochs"]
        half_life_years = (
            half_life_epochs
            * Decimal(cadence_blocks)
            / Decimal(blocks_per_year)
        )
        horizon_issuance: dict[int, int] = {}
        for years in (1, 5, 10, 25):
            height = activation + years * blocks_per_year
            horizon_issuance[years] = (
                scheduled_before(segments, height)
                - scheduled_before(segments, activation)
            )
        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_display_id": scenario_display_id(scenario),
                "scenario_name": scenario["name"],
                "activation_height": activation,
                "subsidy_at_activation_base_units": activation_subsidy,
                "subsidy_at_activation_rin": fmt_decimal(
                    rin(activation_subsidy, coin)
                ),
                "immediate_miner_revenue_shock_pct": fmt_decimal(
                    immediate_shock
                ),
                "consensus_divergence_height": activation,
                "first_later_reduction_height": first_height,
                "first_later_reduction_before_rin": fmt_decimal(rin(before, coin)),
                "first_later_reduction_after_rin": fmt_decimal(rin(after, coin)),
                "first_later_reduction_pct": fmt_decimal(
                    Decimal(before - after) * Decimal(100) / Decimal(before)
                ),
                "normal_scheduled_reduction_pct": fmt_decimal(
                    candidate_parameters[scenario_id]["normal_reduction_pct"]
                ),
                "cadence_blocks": cadence_blocks,
                "cadence_target_years": fmt_decimal(
                    Decimal(cadence_blocks) / Decimal(blocks_per_year)
                ),
                "mathematical_half_life_epochs": fmt_decimal(half_life_epochs),
                "mathematical_half_life_target_years": fmt_decimal(
                    half_life_years
                ),
                "post_activation_issuance_1y_rin": fmt_decimal(
                    rin(horizon_issuance[1], coin)
                ),
                "post_activation_issuance_5y_rin": fmt_decimal(
                    rin(horizon_issuance[5], coin)
                ),
                "post_activation_issuance_10y_rin": fmt_decimal(
                    rin(horizon_issuance[10], coin)
                ),
                "post_activation_issuance_25y_rin": fmt_decimal(
                    rin(horizon_issuance[25], coin)
                ),
                "maximum_scheduled_issuance_base_units": total_scheduled(
                    segments
                ),
                "maximum_scheduled_issuance_rin": fmt_decimal(
                    rin(total_scheduled(segments), coin)
                ),
                "first_zero_subsidy_height": first_zero_height(segments),
            }
        )
    write_csv(root / "data" / "S1_S5B_candidate_comparison.csv", rows)

    s1 = scenario_map["S1"]
    s5b = scenario_map["S5B"]
    s1_first = subsidy_at(built["S1"], activation)
    s1_ratio = Decimal(int(s1["reduction_numerator"])) / Decimal(
        int(s1["reduction_denominator"])
    )
    s1_ideal_post = (
        Decimal(int(net["epoch_blocks"]))
        * rin(s1_first, coin)
        / (Decimal(1) - s1_ratio)
    )

    s5b_anchor = int(s5b["epoch_anchor_height"])
    s5b_epoch = int(s5b["post_activation_epoch_blocks"])
    s5b_initial_blocks = s5b_anchor + s5b_epoch - activation
    s5b_first = subsidy_at(built["S5B"], activation)
    s5b_second = subsidy_at(built["S5B"], s5b_anchor + s5b_epoch)
    s5b_ideal_post = (
        Decimal(s5b_initial_blocks) * rin(s5b_first, coin)
        + Decimal(s5b_epoch)
        * rin(s5b_second, coin)
        / (Decimal(1) - Decimal("0.5"))
    )
    actual_difference = total_scheduled(built["S5B"]) - total_scheduled(
        built["S1"]
    )
    equal_rows = [
        {
            "scenario_id": "S1",
            "scenario_display_id": "S1",
            "ideal_formula": (
                f"{int(net['epoch_blocks'])} * "
                f"{fmt_decimal(rin(s1_first, coin)).rstrip('0').rstrip('.')} / "
                f"(1 - {fmt_decimal(s1_ratio).rstrip('0')})"
            ),
            "ideal_post_activation_issuance_rin": fmt_decimal(s1_ideal_post),
            "integer_post_activation_issuance_rin": fmt_decimal(
                rin(
                    total_scheduled(built["S1"]) - supply_at_activation,
                    coin,
                )
            ),
            "integer_maximum_scheduled_issuance_rin": fmt_decimal(
                rin(total_scheduled(built["S1"]), coin)
            ),
        },
        {
            "scenario_id": "S5B",
            "scenario_display_id": "S5/b",
            "ideal_formula": (
                f"{s5b_initial_blocks} * "
                f"{fmt_decimal(rin(s5b_first, coin)).rstrip('0').rstrip('.')} + "
                f"{s5b_epoch} * "
                f"{fmt_decimal(rin(s5b_second, coin)).rstrip('0').rstrip('.')} / "
                "(1 - 0.5)"
            ),
            "ideal_post_activation_issuance_rin": fmt_decimal(s5b_ideal_post),
            "integer_post_activation_issuance_rin": fmt_decimal(
                rin(
                    total_scheduled(built["S5B"]) - supply_at_activation,
                    coin,
                )
            ),
            "integer_maximum_scheduled_issuance_rin": fmt_decimal(
                rin(total_scheduled(built["S5B"]), coin)
            ),
        },
    ]
    for row in equal_rows:
        row["integer_maximum_difference_s5b_minus_s1_rin"] = fmt_decimal(
            rin(actual_difference, coin)
        )
    write_csv(root / "data" / "S1_S5B_equal_issuance.csv", equal_rows)

    scoring = config["public_review_scoring"][
        "ten_year_scheduled_supply_expansion"
    ]
    current_upper = Decimal(scoring["current_two_point_upper_bound_pct"])
    example_upper = Decimal(
        scoring["robustness_example_two_point_upper_bound_pct"]
    )
    robustness_rows = []
    for row in rows:
        expansion = (
            Decimal(row["post_activation_issuance_10y_rin"])
            * Decimal(100)
            / rin(supply_at_activation, coin)
        )
        robustness_rows.append(
            {
                "scenario_id": row["scenario_id"],
                "scenario_display_id": row["scenario_display_id"],
                "ten_year_scheduled_supply_expansion_pct": fmt_decimal(
                    expansion
                ),
                "current_two_point_upper_bound_pct": fmt_decimal(current_upper),
                "current_points": ten_year_expansion_points(
                    expansion, current_upper
                ),
                "robustness_example_two_point_upper_bound_pct": fmt_decimal(
                    example_upper
                ),
                "points_under_robustness_example": ten_year_expansion_points(
                    expansion, example_upper
                ),
            }
        )
    write_csv(root / "data" / "S1_S5B_score_robustness.csv", robustness_rows)


def export_threshold_crossings(root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]) -> None:
    coin = int(config["network"]["coin_unit_base_units"])
    activation = int(config["network"]["activation_height"])
    blocks_per_year = int(config["network"]["blocks_per_year"])
    rows = []
    for scenario in scenarios:
        segments = built[scenario["id"]]
        for threshold in config["scarcity_thresholds_base_units"]:
            threshold = int(threshold)
            height = first_height_below(segments, threshold)
            rows.append(
                {
                    "scenario_id": scenario["id"],
                    "scenario_display_id": scenario_display_id(scenario),
                    "scenario_name": scenario["name"],
                    "threshold_base_units": threshold,
                    "threshold_rin_display": fmt_decimal(rin(threshold, coin)),
                    "first_height_below_threshold": height or "",
                    "years_after_activation": fmt_decimal(Decimal(height - activation) / Decimal(blocks_per_year), 1) if height is not None else "",
                }
            )
    write_csv(root / "data" / f"{REVISION}threshold_crossings.csv", rows)


def export_scarcity_dilution(root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]) -> None:
    coin = int(config["network"]["coin_unit_base_units"])
    activation = int(config["network"]["activation_height"])
    blocks_per_year = int(config["network"]["blocks_per_year"])
    s0_total = total_scheduled(built["S0"])
    years = [1, 2, 5, 10, 25]
    rows = []
    for scenario in scenarios:
        segments = built[scenario["id"]]
        unbounded = any(segment.perpetual for segment in segments)
        total = total_scheduled(segments)
        row = {
            "scenario_id": scenario["id"],
            "scenario_display_id": scenario_display_id(scenario),
            "scenario_name": scenario["name"],
            "final_scheduled_issuance_rin_display": "" if unbounded else fmt_decimal(rin(total, coin)),
            "post_840k_issuance_rin_display": "" if unbounded else fmt_decimal(rin(total - scheduled_before(segments, activation), coin)),
            "issuance_through_500y_rin_display": fmt_decimal(rin(total, coin)),
            "supply_multiple_relative_to_s0": "" if unbounded else fmt_decimal(Decimal(total) / Decimal(s0_total)),
            "years_until_zero_subsidy": fmt_decimal(Decimal(first_zero_height(segments) - activation) / Decimal(blocks_per_year)) if first_zero_height(segments) is not None else "",
        }
        for y in years:
            start = activation
            end = activation + y * blocks_per_year
            cumulative = issuance_between(segments, start, end)
            annual_at_horizon = issuance_between(segments, end, end + blocks_per_year)
            supply_at_horizon = scheduled_before(segments, end)
            row[f"post_activation_issuance_after_{y}y_rin_display"] = fmt_decimal(rin(cumulative, coin))
            row[f"annual_issuance_at_{y}y_rin_display"] = fmt_decimal(rin(annual_at_horizon, coin))
            row[f"annual_issuance_pct_at_{y}y"] = fmt_decimal(pct(annual_at_horizon, supply_at_horizon))
        rows.append(row)
    write_csv(root / "data" / f"{REVISION}scarcity_dilution_comparison.csv", rows)


def human_number(value: Decimal) -> str:
    value = Decimal(value)
    abs_value = abs(value)
    if abs_value >= Decimal("1000000000"):
        return f"{value / Decimal('1000000000'):.1f}B"
    if abs_value >= Decimal("1000000"):
        return f"{value / Decimal('1000000'):.1f}M"
    if abs_value >= Decimal("1000"):
        return f"{value / Decimal('1000'):.0f}k"
    if abs_value >= Decimal("1"):
        return f"{value:.1f}"
    return f"{value:.3f}"


def draw_line_chart(path: Path, title: str, y_label: str, series: list[tuple[str, tuple[int, int, int], list[tuple[float, float]]]]) -> None:
    width, height = 1900, 980
    margin_left, margin_right, margin_top, margin_bottom = 130, 560, 105, 120
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    x_max = max(max((x for x, _ in points), default=0) for _, _, points in series) or 1
    y_max = max(max((y for _, y in points), default=0) for _, _, points in series) or 1
    y_max *= 1.05

    draw.text((margin_left, 30), title, fill=(20, 20, 20), font=title_font)
    draw.text((20, 70), y_label, fill=(20, 20, 20), font=font)
    draw.text((margin_left + plot_w // 2 - 170, height - 55), "Years after block height 840,000", fill=(20, 20, 20), font=font)

    for i in range(6):
        x = margin_left + i * plot_w / 5
        y = margin_top + i * plot_h / 5
        draw.line((x, margin_top, x, margin_top + plot_h), fill=(225, 225, 225))
        draw.line((margin_left, y, margin_left + plot_w, y), fill=(225, 225, 225))
        x_val = Decimal(str(x_max * i / 5))
        y_val = Decimal(str(y_max * (5 - i) / 5))
        draw.text((x - 12, margin_top + plot_h + 14), f"{x_val:.0f}", fill=(40, 40, 40), font=small_font)
        draw.text((20, y - 8), human_number(y_val), fill=(40, 40, 40), font=small_font)

    draw.rectangle((margin_left, margin_top, margin_left + plot_w, margin_top + plot_h), outline=(80, 80, 80))

    def point_to_xy(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (
            margin_left + (x / x_max) * plot_w,
            margin_top + plot_h - (y / y_max) * plot_h,
        )

    for label, color, points in series:
        xy = [point_to_xy(p) for p in points]
        if len(xy) > 1:
            draw.line(xy, fill=color, width=3)
        elif xy:
            x, y = xy[0]
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)

    legend_x = margin_left + plot_w + 35
    draw.text((legend_x, margin_top), "Scenarios", fill=(20, 20, 20), font=title_font)
    y = margin_top + 45
    for label, color, _ in series:
        draw.rectangle((legend_x, y, legend_x + 28, y + 18), fill=color)
        wrapped = textwrap.wrap(label, width=50) or [label]
        for offset, line in enumerate(wrapped):
            draw.text((legend_x + 40, y + offset * 22), line, fill=(20, 20, 20), font=small_font)
        y += max(45, 24 * len(wrapped) + 12)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def sample_points(config: dict, segments: list[Segment], value_fn, years_after_activation: int | None = None) -> list[tuple[float, float]]:
    activation = int(config["network"]["activation_height"])
    blocks_per_year = int(config["network"]["blocks_per_year"])
    end = plot_end_height(config) if years_after_activation is None else plot_end_height_for_years(config, years_after_activation)
    step = int(config["plot"]["sample_every_blocks"])
    heights = list(range(activation, end + 1, step))
    if heights[-1] != end:
        heights.append(end)
    return [
        (float(Decimal(height - activation) / Decimal(blocks_per_year)), float(value_fn(segments, height)))
        for height in heights
    ]


def export_figures(root: Path, config: dict, scenarios: list[dict], built: dict[str, list[Segment]]) -> None:
    coin = int(config["network"]["coin_unit_base_units"])
    blocks_per_year = int(config["network"]["blocks_per_year"])
    scenario_colors = {s["id"]: tuple(s["color"]) for s in scenarios}

    def all_series(value_fn, years_after_activation: int | None = None):
        return [
            (
                scenario_label(s),
                scenario_colors[s["id"]],
                sample_points(config, built[s["id"]], value_fn, years_after_activation),
            )
            for s in scenarios
        ]

    figure_specs = [
        ("subsidy_by_height", "Maximum permitted subsidy by height", "RIN per block", lambda segments, h: rin(subsidy_at(segments, h), coin)),
        ("cumulative_issuance", "Scheduled issuance by height", "RIN", lambda segments, h: rin(scheduled_before(segments, h), coin)),
        (
            "annual_issuance",
            "Next-year scheduled issuance by height",
            "RIN per 365-day year",
            lambda segments, h: rin(issuance_between(segments, h, h + blocks_per_year), coin),
        ),
        (
            "annual_issuance_pct",
            "Next-year issuance as percentage of scheduled supply",
            "Percent",
            lambda segments, h: pct(issuance_between(segments, h, h + blocks_per_year), scheduled_before(segments, h)),
        ),
    ]

    for slug, title, y_label, value_fn in figure_specs:
        draw_line_chart(
            root / "figures" / f"{REVISION}{slug}_500y.png",
            f"{title} - 500-year structural view",
            y_label,
            all_series(value_fn),
        )
        for years in config["plot"].get("near_term_years", [10, 25]):
            draw_line_chart(
                root / "figures" / f"{REVISION}{slug}_{years}y.png",
                f"{title} - first {years} years",
                y_label,
                all_series(value_fn, int(years)),
            )

    s0_segments = built["S0"]
    draw_line_chart(
        root / "figures" / f"{REVISION}supply_multiple_vs_s0_500y.png",
        "Scheduled supply multiple relative to S0",
        "Multiple",
        all_series(
            lambda segments, h: Decimal(scheduled_before(segments, h)) / Decimal(max(1, scheduled_before(s0_segments, h)))
        ),
    )

def read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def md_alignment(value: str | None) -> str:
    if value is None or value == "":
        return "---"
    normalized = value.lower()
    if normalized in {"left", "l"}:
        return ":---"
    if normalized in {"center", "centre", "c"}:
        return ":---:"
    if normalized in {"right", "r", "numeric", "number"}:
        return "---:"
    if set(normalized) <= {":", "-"} and "-" in normalized:
        return value
    raise ValueError(f"Unsupported markdown table alignment: {value}")


def md_table(
    headers: list[str],
    rows: list[list[str]],
    alignments: list[str | None] | None = None,
    column_relative_widths: list[int] | None = None,
) -> str:
    if alignments is None:
        alignments = [None] * len(headers)
    if len(alignments) != len(headers):
        raise ValueError("Markdown table alignment count must match header count")
    if column_relative_widths is not None:
        if any(
            isinstance(width, bool) or not isinstance(width, int) or width <= 0
            for width in column_relative_widths
        ):
            raise ValueError("Markdown table column widths must be positive integers")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(md_alignment(alignment) for alignment in alignments) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    table = "\n".join(lines) + "\n"
    if column_relative_widths is None:
        return table
    widths = ",".join(str(width) for width in column_relative_widths)
    return table + f'\n: {{tbl-colwidths="[{widths}]"}}\n'


def generated_header(source: str) -> str:
    return f"<!-- Generated by scripts/simulate_monetary_scenarios.py from {source}. Do not edit by hand. -->\n\n"


def export_candidate_whitepaper_includes(
    root: Path,
    config: dict,
    summary_rows: list[dict[str, str]],
    comparison: dict[str, dict[str, str]],
    equal_rows: dict[str, dict[str, str]],
) -> None:
    output = root / "includes" / "whitepaper"
    output.mkdir(parents=True, exist_ok=True)
    summaries = {row["scenario_id"]: row for row in summary_rows}
    source = (
        "data/scenario_config.json, data/scenario_summary.csv, candidate "
        "comparison data, and normative vector artifacts"
    )

    common_parameters = [
        ["Ledger model", "Layer-1 UTXO"],
        ["Consensus mechanism", "Proof of work"],
        ["Proof-of-work function", "RinHash"],
        ["RinHash construction", "BLAKE3 -> Argon2d -> SHA3-256"],
        ["Difficulty adjustment", "Dark Gravity Wave v3"],
        ["Target block interval", "60 seconds"],
        ["Initial block subsidy", "50 RIN"],
        ["Historical reward epoch", "210,000 blocks"],
        [
            "Blocks 0-839,999",
            "Binary integer halving, nominally 50%, with base-unit floor rounding",
        ],
    ]
    candidate_parameters = {
        "S1": [
            [
                "Blocks 840,000 and later",
                "Recursive 19/20 rule every 210,000 blocks; nominally 5%, with per-epoch integer-floor rounding",
            ],
            ["Subsidy floor", "None"],
            [
                "Maximum scheduled issuance",
                f"{summaries['S1']['maximum_scheduled_issuance_rin_display']} RIN",
            ],
        ],
        "S5B": [
            [
                "Post-840,000 phase anchor",
                "Height 630,000; calculation only, no historical rule change",
            ],
            ["Long reward epoch", "2,100,000 blocks"],
            ["Blocks 840,000-2,729,999", "6.25000000 RIN"],
            [
                "Blocks 2,730,000 and later",
                "Binary integer halving every 2,100,000 blocks; nominally 50%, with base-unit floor rounding",
            ],
            ["Subsidy floor", "None"],
            [
                "Maximum scheduled issuance",
                f"{summaries['S5B']['maximum_scheduled_issuance_rin_display']} RIN",
            ],
        ],
        "S6B": [
            ["Blocks 840,000-2,099,999", "4.00000000 RIN"],
            ["Blocks 2,100,000-4,199,999", "2.00000000 RIN"],
            ["Blocks 4,200,000-6,299,999", "1.00000000 RIN"],
            ["Blocks 6,300,000-234,587,499", "0.60000000 RIN"],
            ["Blocks 234,587,500 and later", "0 RIN"],
            ["Underclaimed subsidy", "Not reissued; terminal height unchanged"],
            [
                "Maximum scheduled issuance",
                f"{summaries['S6B']['maximum_scheduled_issuance_rin_display']} RIN",
            ],
        ],
    }
    trailing_parameters = [
        [
            "Historical upper bound stated in the original whitepaper",
            "168,000,000 RIN",
        ],
        ["Premine", "None stated in the original whitepaper"],
        ["Developer tax", "None stated in the original whitepaper"],
    ]
    for scenario_id in ("S1", "S5B", "S6B"):
        (output / f"{scenario_id}_parameter_table.qmd").write_text(
            generated_header(source)
            + md_table(
                ["Parameter", "Value"],
                common_parameters
                + candidate_parameters[scenario_id]
                + trailing_parameters,
                ["left", "left"],
            ),
            encoding="utf-8",
        )

    (output / "S1_abstract_monetary.qmd").write_text(
        generated_header(source)
        + "Rincoin began with a 50 RIN subsidy and 210,000-block reward epochs. "
        + "The first four epochs used binary halving. From block height 840,000, "
        + "the maximum subsidy follows a recursive 19/20 rule, nominally a 5% "
        + "reduction, with integer-floor rounding after each epoch. There is no "
        + "subsidy floor or perpetual tail; "
        + "rounding eventually reduces subsidy to zero. The complete schedule "
        + f"permits at most "
        + f"{summaries['S1']['maximum_scheduled_issuance_rin_display']} RIN.\n",
        encoding="utf-8",
    )
    (output / "S5B_abstract_monetary.qmd").write_text(
        generated_header(source)
        + "Rincoin began with a 50 RIN subsidy and 210,000-block reward epochs. "
        + "The first four epochs used binary halving. For heights at and above "
        + "840,000, the subsidy schedule is phase-aligned to height 630,000 and "
        + "uses 2,100,000-block epochs. Subsidy remains 6.25000000 RIN through "
        + "height 2,729,999 and then follows binary integer halving, nominally "
        + "50%, with floor rounding at base-unit precision. There is no floor "
        + "or perpetual tail. The complete schedule permits at most "
        + f"{summaries['S5B']['maximum_scheduled_issuance_rin_display']} RIN.\n",
        encoding="utf-8",
    )
    (output / "S6B_abstract_monetary.qmd").write_text(
        generated_header(source)
        + "Rincoin began with a 50 RIN subsidy and 210,000-block reward epochs. "
        + "The first four epochs retain the deployed binary-halving rule. From "
        + "height 840,000 the maximum subsidy is 4 RIN, then 2 RIN from height "
        + "2,100,000, 1 RIN from height 4,200,000, and 0.6 RIN from height "
        + "6,300,000 through height 234,587,499. It is zero from height "
        + "234,587,500. The precomputed height-only schedule permits exactly "
        + f"{summaries['S6B']['maximum_scheduled_issuance_rin_display']} RIN.\n",
        encoding="utf-8",
    )

    (output / "S1_monetary_policy.qmd").write_text(
        generated_header(source)
        + "# Monetary Policy\n\n"
        + "The maximum permitted subsidy is a deterministic function of block "
        + "height. The schedule uses integer base units, where one RIN equals "
        + "100,000,000 base units. It does not depend on market or ledger state "
        + "[@rincoinCore2026deployed].\n\n"
        + "Rincoin began with a 50 RIN block subsidy. For blocks below height "
        + "840,000, the subsidy follows the deployed binary-halving rule across "
        + "210,000-block epochs: 50, 25, 12.5, and 6.25 RIN "
        + "[@rincoinCore2026deployed].\n\n"
        + "From block height 840,000, the maximum permitted subsidy follows a "
        + "recursive 19/20 rule, nominally a 5% reduction, with integer-floor "
        + "rounding after each 210,000-block epoch. The first post-840k subsidy "
        + "is 5.93750000 RIN. Each later epoch is calculated from the preceding "
        + "integer-rounded epoch subsidy by multiplying by 19, dividing by 20, "
        + "and rounding down to a whole base unit. Effective reductions can "
        + "differ slightly from 5% after rounding. There is no fixed subsidy "
        + "phase and no perpetual tail. Repeated integer rounding eventually "
        + "produces zero subsidy.\n\n"
        + "The complete height-based schedule permits at most "
        + f"{summaries['S1']['maximum_scheduled_issuance_rin_display']} RIN. "
        + "Final circulating or spendable supply can be lower because unclaimed "
        + "subsidy is not reissued.\n\n"
        + "The original RinCoin whitepaper stated a 168,000,000 RIN maximum "
        + "while also specifying a 50 RIN initial subsidy and 210,000-block "
        + "binary halving. Those parameters produce a "
        + "documentation-versus-consensus inconsistency: unchanged binary "
        + "halving approaches approximately 21 million RIN. The 168 million "
        + "value remains a historical documented upper bound, not the effective "
        + "maximum of this schedule [@rincoinWhitepaper2025; "
        + "@rincoinCore2026deployed].\n\n"
        + "The change at height 840,000 alters future coinbase validation and is "
        + "therefore a hard-fork consensus change. It preserves all valid earlier "
        + "blocks, existing UTXOs, balances, and ownership claims.\n",
        encoding="utf-8",
    )
    (output / "S5B_monetary_policy.qmd").write_text(
        generated_header(source)
        + "# Monetary Policy\n\n"
        + "The maximum permitted subsidy is a deterministic function of block "
        + "height. The schedule uses integer base units, where one RIN equals "
        + "100,000,000 base units. It does not depend on market or ledger state "
        + "[@rincoinCore2026deployed].\n\n"
        + "Rincoin began with a 50 RIN block subsidy. For blocks below height "
        + "840,000, the subsidy follows the deployed binary-halving rule across "
        + "210,000-block epochs: 50, 25, 12.5, and 6.25 RIN "
        + "[@rincoinCore2026deployed].\n\n"
        + "For block heights at and above 840,000, the extended-epoch schedule "
        + "is phase-aligned to height 630,000, the beginning of the existing "
        + "6.25 RIN subsidy period. No block or validation rule below height "
        + "840,000 is changed. The phase length is 2,100,000 blocks. Subsidy "
        + "remains 6.25000000 RIN through height 2,729,999, becomes 3.12500000 "
        + "RIN at height 2,730,000, and then uses binary integer halving, "
        + "nominally 50%, with floor rounding at base-unit precision at each "
        + "later long-epoch boundary. Effective reductions can differ slightly "
        + "from 50% when an odd base-unit value is rounded down. There is no "
        + "floor or perpetual tail, and "
        + "subsidy eventually reaches zero.\n\n"
        + "The complete height-based schedule permits at most "
        + f"{summaries['S5B']['maximum_scheduled_issuance_rin_display']} RIN. "
        + "Final circulating or spendable supply can be lower because unclaimed "
        + "subsidy is not reissued.\n\n"
        + "The original RinCoin whitepaper stated a 168,000,000 RIN maximum "
        + "while also specifying a 50 RIN initial subsidy and 210,000-block "
        + "binary halving. Those parameters produce a "
        + "documentation-versus-consensus inconsistency: unchanged binary "
        + "halving approaches approximately 21 million RIN. The 168 million "
        + "value remains a historical documented upper bound, not the effective "
        + "maximum of this schedule [@rincoinWhitepaper2025; "
        + "@rincoinCore2026deployed].\n\n"
        + "The change at height 840,000 alters future coinbase validation and is "
        + "therefore a hard-fork consensus change. It preserves all valid earlier "
        + "blocks, existing UTXOs, balances, and ownership claims.\n",
        encoding="utf-8",
    )
    (output / "S6B_monetary_policy.qmd").write_text(
        generated_header(source)
        + "# Monetary Policy\n\n"
        + "The maximum permitted subsidy is a deterministic function of block "
        + "height using integer base units, where one RIN is 100,000,000 base "
        + "units. No market, circulating-supply, or actual-issued-supply state "
        + "is an input [@rincoinCore2026deployed].\n\n"
        + "Blocks below height 840,000 retain the deployed binary-halving rule. "
        + "The maximum subsidy is 400,000,000 base units for heights 840,000 "
        + "through 2,099,999; 200,000,000 for heights 2,100,000 through "
        + "4,199,999; 100,000,000 for heights 4,200,000 through 6,299,999; "
        + "and 60,000,000 for heights 6,300,000 through 234,587,499. It is zero "
        + "from height 234,587,500.\n\n"
        + "The terminal height is precomputed from the deployed historical "
        + "schedule and the exact 168,000,000 RIN maximum-scheduled-issuance "
        + "ceiling. Underclaimed subsidy is not reissued and cannot extend the "
        + "final phase. Actual issued, circulating, lost, burned, or dormant "
        + "supply does not affect a later subsidy.\n\n"
        + "This is a deterministic bounded interpretation of Customized Halving "
        + "Scenario II. It does not incorporate the study's governance "
        + "contingency or the separate unbounded implementation snapshot. The "
        + "change at height 840,000 is a hard-fork consensus change and preserves "
        + "all valid earlier blocks, UTXOs, balances, and ownership claims.\n",
        encoding="utf-8",
    )

    (output / "S1_mining_transition.qmd").write_text(
        generated_header(source)
        + "The post-840k schedule replaces each future 50% subsidy cliff with "
        + "a recursive 19/20 step every 210,000 blocks, nominally a 5% reduction "
        + "with integer-floor rounding. This creates frequent but smaller "
        + "changes in nominal subsidy. It does not guarantee stable hashrate or "
        + "network security and schedules more RIN than unchanged binary halving.\n",
        encoding="utf-8",
    )
    (output / "S5B_mining_transition.qmd").write_text(
        generated_header(source)
        + "The post-840k schedule causes no immediate miner-revenue reduction at "
        + "height 840,000 and gives approximately "
        + f"{Decimal(comparison['S5B']['first_later_reduction_height']) - Decimal(config['network']['activation_height']):,.0f} "
        + "blocks before the first later reduction. Each long-epoch boundary then "
        + "reduces subsidy by 50%. This provides a longer adjustment interval but "
        + "does not guarantee that price, fees, or miner economics will absorb "
        + "the later discontinuity.\n",
        encoding="utf-8",
    )
    (output / "S6B_mining_transition.qmd").write_text(
        generated_header(source)
        + "The post-840k schedule reduces the maximum subsidy from 6.25 to 4 RIN "
        + "at activation, then uses predetermined 2, 1, and 0.6 RIN phases. "
        + "The final phase ends at the precomputed height 234,587,500. These "
        + "rules determine maximum coinbase issuance but do not guarantee stable "
        + "hashrate, market value, fees, or network security.\n",
        encoding="utf-8",
    )


def export_generated_includes(root: Path, config: dict) -> None:
    generated = root / "includes"
    generated.mkdir(parents=True, exist_ok=True)

    summary_rows = read_csv_rows(root / "data" / f"{REVISION}scenario_summary.csv")
    scenario_rows = []
    for row in summary_rows:
        scenario_rows.append(
            [
                row["scenario_display_id"],
                row["scenario_name"],
                row["first_activation_subsidy_rin_display"],
                row["maximum_scheduled_issuance_rin_display"] or "unbounded",
                row["post_activation_issuance_rin_display"] or "unbounded",
                row["first_zero_subsidy_height"] or "none",
                row["constant_phase_subsidy_rin_display"] or "none",
                row["ceiling_usage_percent"] or "unbounded",
            ]
        )
    (generated / f"{REVISION}scenario_summary_table.qmd").write_text(
        generated_header(f"data/{REVISION}scenario_summary.csv")
        + md_table(
            [
                "Scenario",
                "Name",
                "First post-840,000 subsidy",
                "Effective maximum scheduled issuance",
                "Post-840,000 issuance",
                "Zero height",
                "Constant phase",
                "Share of original 168M statement",
            ],
            scenario_rows,
            ["center", "left", "right", "right", "right", "right", "right", "right"],
            column_relative_widths=[6, 17, 10, 17, 18, 10, 10, 12],
        ),
        encoding="utf-8",
    )

    constant_rows = []
    for row in summary_rows:
        if row["constant_phase_start_height"]:
            constant_rows.append(
                [
                    row["scenario_display_id"],
                    row["constant_phase_start_height"],
                    row["constant_phase_end_height"] or "perpetual",
                    row["constant_phase_years"] or "perpetual",
                    row["constant_phase_subsidy_rin_display"],
                    row["constant_phase_issuance_rin_display"] or "unbounded",
                    row["constant_phase_share_of_final_scheduled_issuance"] or "unbounded",
                ]
            )
    (generated / f"{REVISION}constant_phase_table.qmd").write_text(
        generated_header(f"data/{REVISION}scenario_summary.csv")
        + md_table(
            ["Scenario", "Starts", "Ends", "Duration, years", "Subsidy", "Issuance in phase", "Share of final bounded issuance"],
            constant_rows,
            ["center", "right", "right", "right", "right", "right", "right"],
            column_relative_widths=[9, 14, 14, 15, 13, 20, 15],
        ),
        encoding="utf-8",
    )

    threshold_rows = read_csv_rows(root / "data" / f"{REVISION}threshold_crossings.csv")
    thresholds_by_scenario = {
        (row["scenario_id"], row["threshold_rin_display"]): row
        for row in threshold_rows
    }
    threshold_summary_rows = []
    for summary in summary_rows:
        cells = [summary["scenario_display_id"]]
        for threshold in ["1.00000000", "0.50000000", "0.10000000", "0.01000000"]:
            row = thresholds_by_scenario[(summary["scenario_id"], threshold)]
            if row["first_height_below_threshold"]:
                cells.append(f"{row['first_height_below_threshold']} ({row['years_after_activation']} y)")
            else:
                cells.append("never")
        if summary["first_zero_subsidy_height"]:
            years = fmt_decimal(
                Decimal(int(summary["first_zero_subsidy_height"]) - int(config["network"]["activation_height"]))
                / Decimal(int(config["network"]["blocks_per_year"])), 1
            )
            cells.append(f"{summary['first_zero_subsidy_height']} ({years} y)")
        else:
            cells.append("none")
        threshold_summary_rows.append(cells)
    (generated / f"{REVISION}threshold_summary_table.qmd").write_text(
        generated_header(f"data/{REVISION}threshold_crossings.csv and data/{REVISION}scenario_summary.csv")
        + md_table(
            ["Scenario", "< 1 RIN", "< 0.5 RIN", "< 0.1 RIN", "< 0.01 RIN", "Zero subsidy"],
            threshold_summary_rows,
            ["center", "right", "right", "right", "right", "right"],
            column_relative_widths=[10, 18, 18, 18, 18, 18],
        ),
        encoding="utf-8",
    )

    horizon_rows = read_csv_rows(root / "data" / f"{REVISION}horizon_table.csv")
    wanted_horizons = {"activation", "1 year", "2 years", "5 years", "10 years", "25 years", "100 years", "terminal height"}
    horizon_snapshot_rows = [
        [
            row["scenario_display_id"],
            row["horizon_label"],
            row["height"],
            row["subsidy_rin_display"],
            row["next_year_issuance_rin_display"],
            row["next_year_issuance_pct_of_scheduled_supply"],
            row["scheduled_issuance_before_height_rin_display"],
            row["remaining_scheduled_issuance_rin_display"],
        ]
        for row in horizon_rows
        if row["horizon_label"] in wanted_horizons
    ]
    (generated / f"{REVISION}horizon_snapshot_table.qmd").write_text(
        generated_header(f"data/{REVISION}horizon_table.csv")
        + md_table(
            [
                "Scenario",
                "Horizon",
                "Height",
                "Subsidy",
                "Next-year issuance",
                "Annual issuance % of scheduled supply",
                "Cumulative scheduled issuance",
                "Remaining scheduled issuance",
            ],
            horizon_snapshot_rows,
            ["center", "center", "right", "right", "right", "right", "right", "right"],
            column_relative_widths=[7, 9, 9, 10, 16, 13, 18, 18],
        ),
        encoding="utf-8",
    )

    boundary_rows = read_csv_rows(root / "data" / f"{REVISION}boundary_vectors.csv")
    wanted_boundary_heights = {"839999", "840000", "840001"}
    activation_boundary_rows = [
        [row["scenario_display_id"], row["height"], row["subsidy_rin_display"], row["scheduled_issuance_before_height_rin_display"]]
        for row in boundary_rows
        if row["height"] in wanted_boundary_heights
    ]
    (generated / f"{REVISION}activation_boundary_table.qmd").write_text(
        generated_header(f"data/{REVISION}boundary_vectors.csv")
        + md_table(
            ["Scenario", "Height", "Subsidy", "Scheduled issuance before height"],
            activation_boundary_rows,
            ["center", "right", "right", "right"],
        ),
        encoding="utf-8",
    )

    scarcity_rows = read_csv_rows(root / "data" / f"{REVISION}scarcity_dilution_comparison.csv")
    dilution_rows = [
        [
            row["scenario_display_id"],
            row["final_scheduled_issuance_rin_display"] or row["issuance_through_500y_rin_display"] + " through 500y",
            row["supply_multiple_relative_to_s0"] or "unbounded",
            row["years_until_zero_subsidy"] or "none",
            row["post_activation_issuance_after_1y_rin_display"],
            row["post_activation_issuance_after_10y_rin_display"],
            row["post_activation_issuance_after_25y_rin_display"],
        ]
        for row in scarcity_rows
    ]
    (generated / f"{REVISION}scarcity_dilution_table.qmd").write_text(
        generated_header(f"data/{REVISION}scarcity_dilution_comparison.csv")
        + md_table(
            [
                "Scenario",
                "Final or 500-year issuance",
                "Supply multiple vs S0",
                "Years to zero",
                "Post-840,000 issuance after 1 year",
                "After 10 years",
                "After 25 years",
            ],
            dilution_rows,
            ["center", "right", "right", "right", "right", "right", "right"],
            column_relative_widths=[8, 18, 13, 13, 14, 16, 16],
        ),
        encoding="utf-8",
    )

    half_life = read_csv_rows(root / "data" / "s1_subsidy_half_life.csv")[0]
    (generated / "s1_half_life_table.qmd").write_text(
        generated_header("data/s1_subsidy_half_life.csv")
        + md_table(
            ["Metric", "Value", "Status"],
            [
                [
                    "Nominal reduction per epoch",
                    "5%",
                    "recursive 19/20 rule with integer-floor rounding",
                ],
                [
                    "Mathematical subsidy half-life",
                    f"{half_life['mathematical_half_life_epochs']} epochs",
                    half_life["metric_status"],
                ],
                [
                    "Mathematical subsidy half-life",
                    f"{half_life['mathematical_half_life_target_years']} target years",
                    "365-day / 525,600-block year convention",
                ],
            ],
            ["left", "right", "left"],
        ),
        encoding="utf-8",
    )

    half_life = read_csv_rows(root / "data" / "s0_subsidy_half_life.csv")[0]
    (generated / "s0_half_life_table.qmd").write_text(
        generated_header("data/s0_subsidy_half_life.csv")
        + md_table(
            ["Metric", "Value", "Status"],
            [
                [
                    "Nominal reduction per epoch",
                    "50%",
                    "recursive halving rule with integer-floor rounding",
                ],
                [
                    "Mathematical subsidy half-life",
                    f"{half_life['mathematical_half_life_epochs']} epochs",
                    half_life["metric_status"],
                ],
                [
                    "Mathematical subsidy half-life",
                    f"{half_life['mathematical_half_life_target_years']} target years",
                    "365-day / 525,600-block year convention",
                ],
            ],
            ["left", "right", "left"],
        ),
        encoding="utf-8",
    )

    comparison = {
        row["scenario_id"]: row
        for row in read_csv_rows(
            root / "data" / "S1_S5B_candidate_comparison.csv"
        )
    }
    comparison_metrics = [
        (
            "Subsidy at activation",
            "subsidy_at_activation_rin",
            lambda value: f"{value} RIN",
        ),
        (
            "Immediate miner-revenue shock",
            "immediate_miner_revenue_shock_pct",
            lambda value: f"{Decimal(value):.0f}%",
        ),
        (
            "Consensus divergence height",
            "consensus_divergence_height",
            lambda value: f"{int(value):,}",
        ),
        (
            "First later reduction",
            "first_later_reduction_height",
            lambda value: f"height {int(value):,}",
        ),
        (
            "First later reduction amount",
            "first_later_reduction_pct",
            lambda value: f"{Decimal(value):.0f}%",
        ),
        (
            "Nominal ordinary reduction",
            "normal_scheduled_reduction_pct",
            lambda value: f"{Decimal(value):.0f}%",
        ),
        (
            "Cadence",
            "cadence_blocks",
            lambda value: f"{int(value):,} blocks",
        ),
        (
            "Mathematical half-life",
            "mathematical_half_life_epochs",
            lambda value: f"{value} epochs",
        ),
        (
            "Mathematical half-life",
            "mathematical_half_life_target_years",
            lambda value: f"~{Decimal(value):.1f} target years",
        ),
        (
            "Post-activation issuance after 1 year",
            "post_activation_issuance_1y_rin",
            lambda value: f"{value} RIN",
        ),
        (
            "Post-activation issuance after 5 years",
            "post_activation_issuance_5y_rin",
            lambda value: f"{value} RIN",
        ),
        (
            "Post-activation issuance after 10 years",
            "post_activation_issuance_10y_rin",
            lambda value: f"{value} RIN",
        ),
        (
            "Post-activation issuance after 25 years",
            "post_activation_issuance_25y_rin",
            lambda value: f"{value} RIN",
        ),
        (
            "Maximum scheduled issuance",
            "maximum_scheduled_issuance_rin",
            lambda value: f"{value} RIN",
        ),
        (
            "First zero-subsidy height",
            "first_zero_subsidy_height",
            lambda value: f"{int(value):,}",
        ),
    ]
    (generated / "S1_S5B_candidate_comparison_table.qmd").write_text(
        generated_header("data/S1_S5B_candidate_comparison.csv")
        + md_table(
            ["Metric", "S1", "S5/b"],
            [
                [
                    label,
                    formatter(comparison["S1"][field]),
                    formatter(comparison["S5B"][field]),
                ]
                for label, field, formatter in comparison_metrics
            ],
            ["left", "right", "right"],
        ),
        encoding="utf-8",
    )

    equal_rows = {
        row["scenario_id"]: row
        for row in read_csv_rows(root / "data" / "S1_S5B_equal_issuance.csv")
    }
    ideal_total = Decimal(
        equal_rows["S1"]["ideal_post_activation_issuance_rin"]
    )
    max_difference = Decimal(
        equal_rows["S1"]["integer_maximum_difference_s5b_minus_s1_rin"]
    )
    (generated / "S1_S5B_equal_issuance_derivation.qmd").write_text(
        generated_header("data/S1_S5B_equal_issuance.csv")
        + "For S1, the ideal real-number post-840,000 total is:\n\n"
        + f"`{equal_rows['S1']['ideal_formula']} = {ideal_total:,.0f} RIN`\n\n"
        + "For S5/b, the ideal real-number post-840,000 total is:\n\n"
        + f"`{equal_rows['S5B']['ideal_formula']} = {ideal_total:,.0f} RIN`\n\n"
        + "Integer consensus arithmetic produces:\n\n"
        + f"- S1 maximum scheduled issuance: "
        + f"`{Decimal(equal_rows['S1']['integer_maximum_scheduled_issuance_rin']):,.8f} RIN`;\n"
        + f"- S5/b maximum scheduled issuance: "
        + f"`{Decimal(equal_rows['S5B']['integer_maximum_scheduled_issuance_rin']):,.8f} RIN`;\n"
        + f"- S5/b minus S1: `{max_difference:,.8f} RIN`.\n\n"
        + "The ideal post-activation totals are equal. The small integer-result "
        + "difference comes from their different rounding paths. The policy "
        + "choice is therefore primarily about issuance timing and shape rather "
        + "than final amount: S1 uses recurring 19/20 reductions, nominally 5%, "
        + "while S5/b front-loads more issuance and then applies four-year binary "
        + "integer halvings, nominally 50%.\n",
        encoding="utf-8",
    )

    robustness = {
        row["scenario_id"]: row
        for row in read_csv_rows(root / "data" / "S1_S5B_score_robustness.csv")
    }
    (generated / "S1_S5B_score_robustness.qmd").write_text(
        generated_header("data/S1_S5B_score_robustness.csv")
        + "S1's ten-year scheduled supply expansion is "
        + f"`{fmt_decimal(Decimal(robustness['S1']['ten_year_scheduled_supply_expansion_pct']),2)}%` "
        + "of pre-activation scheduled supply; S5/b's is "
        + f"`{fmt_decimal(Decimal(robustness['S5B']['ten_year_scheduled_supply_expansion_pct']),2)}%`. "
        + "The current two-point interval ends at "
        + f"`{fmt_decimal(Decimal(robustness['S1']['current_two_point_upper_bound_pct']),2)}%`, so S1 "
        + f"receives {robustness['S1']['current_points']} points and S5/b "
        + f"receives {robustness['S5B']['current_points']}. Moving only that "
        + "boundary to "
        + f"`{fmt_decimal(Decimal(robustness['S5B']['robustness_example_two_point_upper_bound_pct']),2)}%` "
        + "would increase S5/b by one point without changing any monetary "
        + "result. Numerical totals are compact policy indicators, not "
        + "objective proof of superiority, and they do not include milestone "
        + "or social-coordination considerations.\n",
        encoding="utf-8",
    )

    vector_rows = read_csv_rows(root / "data" / "S1_normative_test_vectors.csv")
    (generated / "S1_normative_vectors_table.qmd").write_text(
        generated_header(
            "data/S1_normative_test_vectors.csv and "
            "data/S1_normative_test_vectors.json"
        )
        + md_table(
            [
                "Vector",
                "Height",
                "Epoch",
                "Recurrence input",
                "Maximum subsidy, base units",
                "Maximum subsidy, RIN",
                "Boundary purpose",
            ],
            [
                [
                    row["vector_id"],
                    row["height"],
                    row["post_activation_epoch_index"],
                    row["recurrence_input_subsidy_base_units"] or "n/a",
                    row["maximum_permitted_subsidy_base_units"],
                    row["maximum_permitted_subsidy_rin"],
                    row["notes"],
                ]
                for row in vector_rows
            ],
            ["center", "right", "right", "right", "right", "right", "left"],
        ),
        encoding="utf-8",
    )

    vector_hashes = [
        line.split(maxsplit=1)
        for line in (root / "data" / "S1_normative_test_vectors.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    (generated / "S1_vector_hashes_table.qmd").write_text(
        generated_header("data/S1_normative_test_vectors.sha256")
        + md_table(
            ["Artifact", "SHA-256"],
            [[path.strip(), digest] for digest, path in vector_hashes],
            ["left", "left"],
        ),
        encoding="utf-8",
    )

    s5b_vector_rows = read_csv_rows(
        root / "data" / "S5B_normative_test_vectors.csv"
    )
    (generated / "S5B_normative_vectors_table.qmd").write_text(
        generated_header(
            "data/S5B_normative_test_vectors.csv and "
            "data/S5B_normative_test_vectors.json"
        )
        + md_table(
            [
                "Vector",
                "Height",
                "Long-epoch index",
                "Phase anchor",
                "Maximum subsidy, base units",
                "Maximum subsidy, RIN",
                "Boundary purpose",
            ],
            [
                [
                    row["vector_id"],
                    row["height"],
                    row["long_epoch_index"],
                    row["phase_anchor_height"] or "n/a",
                    row["maximum_permitted_subsidy_base_units"],
                    row["maximum_permitted_subsidy_rin"],
                    row["notes"],
                ]
                for row in s5b_vector_rows
            ],
            ["center", "right", "right", "right", "right", "right", "left"],
        ),
        encoding="utf-8",
    )

    s5b_vector_hashes = [
        line.split(maxsplit=1)
        for line in (root / "data" / "S5B_normative_test_vectors.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    (generated / "S5B_vector_hashes_table.qmd").write_text(
        generated_header("data/S5B_normative_test_vectors.sha256")
        + md_table(
            ["Artifact", "SHA-256"],
            [[path.strip(), digest] for digest, path in s5b_vector_hashes],
            ["left", "left"],
        ),
        encoding="utf-8",
    )

    s6b_vector_rows = read_csv_rows(
        root / "data" / "S6B_normative_test_vectors.csv"
    )
    (generated / "S6B_normative_vectors_table.qmd").write_text(
        generated_header(
            "data/S6B_normative_test_vectors.csv and "
            "data/S6B_normative_test_vectors.json"
        )
        + md_table(
            [
                "Vector",
                "Height",
                "Phase",
                "Maximum subsidy, base units",
                "Maximum subsidy, RIN",
                "Cumulative before, RIN",
                "Cumulative after, RIN",
                "Boundary purpose",
            ],
            [
                [
                    row["vector_id"],
                    row["height"],
                    row["phase_identifier"],
                    row["maximum_subsidy_base_units"],
                    row["maximum_subsidy_rin"],
                    row["cumulative_maximum_scheduled_issuance_before_block_rin"],
                    row["cumulative_maximum_scheduled_issuance_after_block_rin"],
                    row["notes"],
                ]
                for row in s6b_vector_rows
            ],
            ["center", "right", "left", "right", "right", "right", "right", "left"],
        ),
        encoding="utf-8",
    )

    s6b_vector_hashes = [
        line.split(maxsplit=1)
        for line in (root / "data" / "S6B_normative_test_vectors.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    (generated / "S6B_vector_hashes_table.qmd").write_text(
        generated_header("data/S6B_normative_test_vectors.sha256")
        + md_table(
            ["Artifact", "SHA-256"],
            [[path.strip(), digest] for digest, path in s6b_vector_hashes],
            ["left", "left"],
        ),
        encoding="utf-8",
    )

    export_candidate_whitepaper_includes(
        root, config, summary_rows, comparison, equal_rows
    )


def validate_generated_includes(root: Path) -> None:
    summary = {row["scenario_id"]: row for row in read_csv_rows(root / "data" / f"{REVISION}scenario_summary.csv")}
    boundary_rows = read_csv_rows(root / "data" / f"{REVISION}boundary_vectors.csv")
    boundary = {(row["scenario_id"], row["height"]): row for row in boundary_rows}
    threshold_rows = read_csv_rows(root / "data" / f"{REVISION}threshold_crossings.csv")
    thresholds = {(row["scenario_id"], row["threshold_rin_display"]): row for row in threshold_rows}

    scenario_table = (root / "includes" / f"{REVISION}scenario_summary_table.qmd").read_text(encoding="utf-8")
    assert summary["S1"]["maximum_scheduled_issuance_rin_display"] in scenario_table
    assert summary["S2a"]["scenario_name"] in scenario_table
    assert summary["S5a"]["scenario_name"] in scenario_table
    assert summary["S5B"]["scenario_name"] in scenario_table
    assert summary["S6B"]["scenario_name"] in scenario_table
    assert summary["S7"]["scenario_name"] in scenario_table

    boundary_table = (root / "includes" / f"{REVISION}activation_boundary_table.qmd").read_text(encoding="utf-8")
    assert boundary[("S0", "840000")]["subsidy_rin_display"] in boundary_table
    assert boundary[("S1", "840000")]["subsidy_rin_display"] in boundary_table
    assert boundary[("S2a", "840000")]["subsidy_rin_display"] in boundary_table

    threshold_table = (root / "includes" / f"{REVISION}threshold_summary_table.qmd").read_text(encoding="utf-8")
    assert thresholds[("S1", "0.10000000")]["years_after_activation"] in threshold_table
    assert thresholds[("S2a", "0.10000000")]["years_after_activation"] in threshold_table

    vector_rows = read_csv_rows(root / "data" / "S1_normative_test_vectors.csv")
    vectors = {int(row["height"]): row for row in vector_rows}
    assert vectors[839_999]["maximum_permitted_subsidy_base_units"] == "625000000"
    assert vectors[840_000]["maximum_permitted_subsidy_base_units"] == "593750000"
    assert vectors[8_190_000]["maximum_permitted_subsidy_base_units"] == "98612003"
    assert vectors[11_130_000]["maximum_permitted_subsidy_base_units"] == "48090601"
    assert vectors[17_640_000]["maximum_permitted_subsidy_base_units"] == "9805995"
    assert vectors[73_709_999]["maximum_permitted_subsidy_base_units"] == "1"
    assert vectors[73_710_000]["maximum_permitted_subsidy_base_units"] == "0"

    s5b_vector_rows = read_csv_rows(
        root / "data" / "S5B_normative_test_vectors.csv"
    )
    s5b_vectors = {int(row["height"]): row for row in s5b_vector_rows}
    assert (
        s5b_vectors[839_999]["maximum_permitted_subsidy_base_units"]
        == "625000000"
    )
    assert (
        s5b_vectors[840_000]["maximum_permitted_subsidy_base_units"]
        == "625000000"
    )
    assert (
        s5b_vectors[2_729_999]["maximum_permitted_subsidy_base_units"]
        == "625000000"
    )
    assert (
        s5b_vectors[2_730_000]["maximum_permitted_subsidy_base_units"]
        == "312500000"
    )
    assert (
        s5b_vectors[63_629_999]["maximum_permitted_subsidy_base_units"] == "1"
    )
    assert (
        s5b_vectors[63_630_000]["maximum_permitted_subsidy_base_units"] == "0"
    )

    s6b_vector_rows = read_csv_rows(
        root / "data" / "S6B_normative_test_vectors.csv"
    )
    s6b_vectors = {int(row["height"]): row for row in s6b_vector_rows}
    for height, expected in {
        839_999: "625000000",
        840_000: "400000000",
        2_100_000: "200000000",
        4_200_000: "100000000",
        6_300_000: "60000000",
        234_587_499: "60000000",
        234_587_500: "0",
    }.items():
        assert s6b_vectors[height]["maximum_subsidy_base_units"] == expected

    comparison_table = (
        root / "includes" / "S1_S5B_candidate_comparison_table.qmd"
    ).read_text(encoding="utf-8")
    assert summary["S1"]["maximum_scheduled_issuance_rin_display"] in comparison_table
    assert summary["S5B"]["maximum_scheduled_issuance_rin_display"] in comparison_table

    equal_derivation = (
        root / "includes" / "S1_S5B_equal_issuance_derivation.qmd"
    ).read_text(encoding="utf-8")
    assert "24,937,500 RIN" in equal_derivation
    assert "6.75150000 RIN" in equal_derivation


def assert_config_has_no_dynamic_consensus_inputs(config: dict) -> None:
    forbidden = {
        "actual_minted_supply",
        "actual_coinbase_outputs",
        "circulating_supply",
        "spendable_supply",
        "utxo_supply",
        "burned_coins",
        "lost_coins",
        "dormant_coins",
        "underclaimed_subsidy",
        "transaction_fees",
    }
    serialized_scenarios = json.dumps(config["scenarios"]).lower()
    for key in forbidden:
        assert key not in serialized_scenarios, f"Forbidden dynamic consensus key in scenarios: {key}"


def run_assertions(config: dict, built: dict[str, list[Segment]]) -> None:
    coin = int(config["network"]["coin_unit_base_units"])
    ceiling = int(config["network"]["maximum_supply_ceiling_base_units"])
    activation = int(config["network"]["activation_height"])
    expected = config["expected_assertions"]
    assert_config_has_no_dynamic_consensus_inputs(config)

    for scenario_id, checks in expected.items():
        segments = built[scenario_id]
        if "first_activation_subsidy_base_units" in checks:
            assert subsidy_at(segments, activation) == int(checks["first_activation_subsidy_base_units"]), scenario_id
        if "first_zero_subsidy_height" in checks:
            assert first_zero_height(segments) == int(checks["first_zero_subsidy_height"]), scenario_id
        if "maximum_scheduled_issuance_base_units" in checks:
            assert total_scheduled(segments) == int(checks["maximum_scheduled_issuance_base_units"]), scenario_id
        if "floor_start_height" in checks:
            phase = constant_phase(segments)
            assert phase and phase.start_height == int(checks["floor_start_height"]), scenario_id
        if "undershoot_base_units" in checks:
            assert ceiling - total_scheduled(segments) == int(checks["undershoot_base_units"]), scenario_id
        if checks.get("unbounded"):
            assert any(segment.perpetual for segment in segments), scenario_id
        if "terminal_phase_start_height" in checks:
            phase = constant_phase(segments)
            assert phase and phase.start_height == int(checks["terminal_phase_start_height"]), scenario_id
        if "terminal_subsidy_base_units" in checks:
            phase = constant_phase(segments)
            assert phase and phase.subsidy_base_units == int(checks["terminal_subsidy_base_units"]), scenario_id

    for scenario_id, segments in built.items():
        if not any(segment.perpetual for segment in segments):
            assert total_scheduled(segments) <= ceiling, scenario_id
    assert subsidy_at(built["S1"], activation) == 593_750_000
    assert first_height_below(built["S1"], coin) == 8_190_000
    assert first_height_below(built["S1"], coin // 2) == 11_130_000
    assert subsidy_at(built["S5a"], activation) == 312_500_000
    assert subsidy_at(built["S5a"], 2_939_999) == 312_500_000
    assert subsidy_at(built["S5a"], 2_940_000) == 156_250_000
    assert subsidy_at(built["S5B"], activation) == 625_000_000
    assert subsidy_at(built["S5B"], 2_729_999) == 625_000_000
    assert subsidy_at(built["S5B"], 2_730_000) == 312_500_000
    assert first_zero_height(built["S5B"]) == 63_630_000
    assert subsidy_at(built["S2b"], 8_189_999) == 103_802_109
    assert subsidy_at(built["S2b"], 8_190_000) == coin
    assert subsidy_at(built["S2b"], 135_706_703) == coin
    assert subsidy_at(built["S2b"], 135_706_704) == 0
    assert subsidy_at(built["S6a"], 840_000) == 400_000_000
    assert subsidy_at(built["S6a"], 6_300_000) == 50_000_000
    assert subsidy_at(built["S6B"], 6_300_000) == 60_000_000
    assert first_zero_height(built["S6B"]) == 234_587_500
    assert total_scheduled(built["S6B"]) == ceiling
    assert subsidy_at(built["S6c"], 6_300_000) == coin
    assert subsidy_at(built["S6c"], 8_400_000) == 60_000_000
    assert subsidy_at(built["S7"], 6_300_000) == 60_000_000
    assert any(segment.perpetual for segment in built["S7"])


def main() -> None:
    root = Path.cwd()
    config = load_config(root)
    scenarios = config["scenarios"]
    built = {scenario["id"]: build_segments(config, scenario) for scenario in scenarios}

    run_assertions(config, built)
    remove_stale_segment_exports(root, scenarios)
    remove_stale_candidate_exports(root)

    for scenario in scenarios:
        export_segments(root, config, scenario, built[scenario["id"]])

    write_csv(root / "data" / f"{REVISION}scenario_summary.csv", scenario_summary(config, scenarios, built))
    export_horizon_table(root, config, scenarios, built)
    export_boundary_vectors(root, config, scenarios, built)
    export_threshold_crossings(root, config, scenarios, built)
    export_scarcity_dilution(root, config, scenarios, built)
    export_s0_half_life(root, config, scenarios)
    export_s1_half_life(root, config, scenarios)
    export_s1_normative_vectors(root, config, scenarios, built)
    export_s5b_normative_vectors(root, config, scenarios, built)
    export_s6b_normative_vectors(root, config, scenarios, built)
    export_s1_s5b_comparison(root, config, scenarios, built)
    export_figures(root, config, scenarios, built)
    export_generated_includes(root, config)
    validate_generated_includes(root)


if __name__ == "__main__":
    main()
