#!/usr/bin/env python3
"""Generate stable empirical market and miner-behaviour review artifacts.

All network and API inputs are frozen by separate collectors. This analyzer is
offline and deterministic for a given configuration and evidence snapshot.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import html
import json
import math
import re
import statistics
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

import analyze_empirical_snapshot as base
import simulate_monetary_scenarios as monetary


getcontext().prec = 80
REVISION = ""
D = Decimal
COIN = D(100_000_000)
SECONDS_PER_DAY = 86_400
HALVING_HEIGHTS = (210_000, 420_000, 630_000)
HALVING_SUBSIDIES = {
    210_000: (D("50"), D("25")),
    420_000: (D("25"), D("12.5")),
    630_000: (D("12.5"), D("6.25")),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fmt(value: Decimal | float | int, places: int = 8) -> str:
    return f"{D(str(value)).quantize(D(1).scaleb(-places)):f}"


def fmt_optional(value: Decimal | float | int | None, places: int = 8) -> str:
    return "" if value is None else fmt(value, places)


def unix_to_utc(timestamp: int) -> str:
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def utc_date(timestamp: int) -> date:
    return datetime.fromtimestamp(timestamp, timezone.utc).date()


def parse_iso_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def percentile(values: list[float | int], fraction: float) -> float:
    return base.percentile(values, fraction)


def stats(values: list[float | int]) -> dict[str, float]:
    return base.stats(values)


def generated_include(
    root: Path,
    name: str,
    source: str,
    headers: list[str],
    rows: list[list[str]],
    alignments: list[str],
    column_relative_widths: list[int] | None = None,
) -> None:
    base.write_include(
        root,
        name,
        source,
        headers,
        rows,
        alignments,
        column_relative_widths=column_relative_widths,
    )


def manifest_file_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def verify_manifest(root: Path, manifest_path: Path) -> list[dict[str, Any]]:
    manifest = read_json(manifest_path)
    rows = []
    for item in manifest["files"]:
        path = manifest_file_path(root, str(item["path"]))
        actual = sha256(path)
        if actual != item["sha256"]:
            raise ValueError(f"Frozen source hash mismatch: {path}")
        rows.append(
            {
                "path": str(path.relative_to(root))
                if path.is_relative_to(root)
                else str(path),
                "source_url": item["source_url"],
                "retrieved_utc": item["retrieved_utc"],
                "http_status": item["http_status"],
                "bytes": item["bytes"],
                "sha256": actual,
                "evidence_class": "directly observed from a frozen source",
            }
        )
    return rows


def manifest_entry(manifest: dict[str, Any], suffix: str) -> dict[str, Any]:
    matches = [
        row for row in manifest["files"] if str(row["path"]).endswith("/" + suffix)
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one manifest entry for {suffix}: {len(matches)}")
    return matches[0]


def confidence_definition_rows() -> list[dict[str, str]]:
    return [
        {
            "flag": "high",
            "criteria": (
                "Price, executed trades, spread and depth are available from the "
                "same venue and period; reported volume exceeds 1,000 USD/day; "
                "the last meaningful trade is no more than one day old."
            ),
        },
        {
            "flag": "medium",
            "criteria": (
                "Price and executed volume exceed 100 USD/day, with at least one "
                "direct liquidity control (trade count, spread or depth); no "
                "material data gap overlaps the window."
            ),
        },
        {
            "flag": "low",
            "criteria": (
                "A price exists, but volume is positive and at most 100 USD/day, "
                "historical spread/depth is absent, or staleness cannot be ruled out."
            ),
        },
        {
            "flag": "unusable",
            "criteria": (
                "An anchor price is missing, reported volume is zero with no "
                "executed-trade evidence, or a material data gap spans the event."
            ),
        },
    ]


def export_price_history(
    root: Path,
    snapshot_dir: Path,
    market_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[date, dict[str, Any]]]:
    rin_rows = read_json(snapshot_dir / "coinpaprika_rin_history_daily.json")
    btc_rows = read_json(snapshot_dir / "coinpaprika_btc_history_daily.json")
    rin_by_date = {parse_iso_date(str(row["timestamp"])): row for row in rin_rows}
    btc_by_date = {parse_iso_date(str(row["timestamp"])): row for row in btc_rows}
    start = date.fromisoformat(market_config["price_history_start"])
    end = date.fromisoformat(market_config["price_history_end"])
    low_threshold = D(market_config["low_reported_volume_usd_threshold"])
    meaningful_threshold = D(
        market_config["meaningful_trade_volume_usd_threshold"]
    )
    last_meaningful: date | None = None
    exported: list[dict[str, Any]] = []
    indexed: dict[date, dict[str, Any]] = {}

    for day in daterange(start, end):
        rin = rin_by_date.get(day)
        btc = btc_by_date.get(day)
        rin_usd = D(str(rin["price"])) if rin else None
        btc_usd = D(str(btc["price"])) if btc else None
        rin_btc = (
            rin_usd / btc_usd
            if rin_usd is not None and btc_usd not in (None, D(0))
            else None
        )
        volume = D(str(rin["volume_24h"])) if rin else None
        if volume is not None and volume >= meaningful_threshold:
            last_meaningful = day
        days_since = (day - last_meaningful).days if last_meaningful else None
        if rin is None:
            confidence = "unusable"
        elif volume == 0:
            confidence = "low"
        elif volume is not None and volume <= low_threshold:
            confidence = "low"
        else:
            # Aggregated historical ticks do not carry direct spread/depth.
            confidence = "low"
        row = {
            "date_utc": day.isoformat(),
            "rin_usd_historical_tick": fmt_optional(rin_usd, 12),
            "btc_usd_historical_tick": fmt_optional(btc_usd, 8),
            "rin_btc_derived": fmt_optional(rin_btc, 16),
            "reported_volume_24h_usd": fmt_optional(volume, 8),
            "market_cap_usd": (
                fmt(D(str(rin["market_cap"])), 8) if rin else ""
            ),
            "missing_rin_price": str(rin is None).lower(),
            "missing_btc_price": str(btc is None).lower(),
            "zero_reported_volume": str(volume == 0 if volume is not None else False).lower(),
            "low_reported_volume": str(
                volume is not None and volume <= low_threshold
            ).lower(),
            "days_since_last_reported_volume_at_least_100_usd": (
                "" if days_since is None else days_since
            ),
            "market_data_confidence": confidence,
            "source": "CoinPaprika daily historical API",
            "price_semantics": "daily historical tick; not asserted to be exchange close",
            "evidence_class": "directly observed from a frozen public source",
        }
        exported.append(row)
        indexed[day] = {
            **row,
            "rin_usd": rin_usd,
            "btc_usd": btc_usd,
            "rin_btc": rin_btc,
            "volume_usd": volume,
        }

    write_csv(root / "data" / f"{REVISION}rin_daily_price_volume.csv", exported)
    write_csv(
        root / "data" / f"{REVISION}market_data_confidence_criteria.csv",
        confidence_definition_rows(),
    )
    return exported, indexed


def iter_jsonl_gz(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def export_halving_chain_rows(
    root: Path,
    base_snapshot: Path,
    market_snapshot: Path,
    halving_blocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    event_times = {
        int(row["height"]): int(row["header"]["time"]) for row in halving_blocks
    }
    min_time = min(event_times.values()) - 31 * SECONDS_PER_DAY
    max_time = max(event_times.values()) + 31 * SECONDS_PER_DAY
    paths = [
        market_snapshot / "node_first_halving_pre30d_extension.jsonl.gz",
        base_snapshot / "node_block_history_365d.jsonl.gz",
    ]
    rolling: deque[tuple[int, int, int]] = deque(maxlen=121)
    previous_time: int | None = None
    exported: list[dict[str, Any]] = []
    seen_heights: set[int] = set()

    for path in paths:
        for row in iter_jsonl_gz(path):
            height = int(row["height"])
            if height in seen_heights:
                continue
            seen_heights.add(height)
            timestamp = int(row["time"])
            chainwork = int(str(row["chainwork"]), 16)
            rolling.append((height, timestamp, chainwork))
            rolling_hashrate: Decimal | None = None
            if len(rolling) == 121:
                first = rolling[0]
                elapsed = timestamp - first[1]
                if elapsed > 0:
                    rolling_hashrate = D(chainwork - first[2]) / D(elapsed)
            block_interval = (
                timestamp - previous_time if previous_time is not None else None
            )
            previous_time = timestamp
            if not (min_time <= timestamp <= max_time):
                continue
            nearest_height = min(
                event_times, key=lambda candidate: abs(timestamp - event_times[candidate])
            )
            if abs(timestamp - event_times[nearest_height]) > 31 * SECONDS_PER_DAY:
                continue
            exported.append(
                {
                    "halving_height": nearest_height,
                    "height": height,
                    "time_unix": timestamp,
                    "time_utc": unix_to_utc(timestamp),
                    "days_from_halving": fmt(
                        D(timestamp - event_times[nearest_height]) / D(SECONDS_PER_DAY),
                        8,
                    ),
                    "difficulty": fmt(D(str(row["difficulty"])), 12),
                    "block_interval_seconds": (
                        "" if block_interval is None else block_interval
                    ),
                    "rolling_120_block_hashrate_mhps": (
                        ""
                        if rolling_hashrate is None
                        else fmt(rolling_hashrate / D(1_000_000), 8)
                    ),
                    "subsidy_base_units": int(row["subsidy_base_units"]),
                    "total_fees_base_units": int(row["total_fees_base_units"]),
                    "non_coinbase_transactions": int(
                        row["non_coinbase_transactions"]
                    ),
                    "evidence_class": "directly observed from the local synchronized node",
                }
            )

    output = root / "data" / f"{REVISION}halving_chain_observations.csv.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(exported[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(exported)
    return exported, event_times


def window_rows(
    rows: list[dict[str, Any]],
    event_height: int,
    event_time: int,
    days: int,
    side: str,
) -> list[dict[str, Any]]:
    width = days * SECONDS_PER_DAY
    if side == "pre":
        return [
            row
            for row in rows
            if int(row["halving_height"]) == event_height
            and event_time - width <= int(row["time_unix"]) < event_time
        ]
    return [
        row
        for row in rows
        if int(row["halving_height"]) == event_height
        and event_time <= int(row["time_unix"]) < event_time + width
    ]


def aggregate_chain_window(
    rows: list[dict[str, Any]],
    prices: dict[date, dict[str, Any]],
) -> dict[str, Any]:
    hashrates = [
        float(row["rolling_120_block_hashrate_mhps"])
        for row in rows
        if row["rolling_120_block_hashrate_mhps"] != ""
    ]
    intervals = [
        int(row["block_interval_seconds"])
        for row in rows
        if row["block_interval_seconds"] != ""
        and 0 <= int(row["block_interval_seconds"]) <= 86_400
    ]
    fees = [int(row["total_fees_base_units"]) for row in rows]
    transactions = [int(row["non_coinbase_transactions"]) for row in rows]
    difficulties = [float(row["difficulty"]) for row in rows]
    revenue_rin = [
        D(int(row["subsidy_base_units"]) + int(row["total_fees_base_units"])) / COIN
        for row in rows
    ]
    revenue_usd = []
    for row, revenue in zip(rows, revenue_rin):
        price = prices.get(utc_date(int(row["time_unix"])), {}).get("rin_usd")
        if price is not None:
            revenue_usd.append(float(revenue * price))
    return {
        "blocks": len(rows),
        "mean_hashrate_mhps": statistics.fmean(hashrates) if hashrates else None,
        "median_hashrate_mhps": statistics.median(hashrates) if hashrates else None,
        "mean_difficulty": statistics.fmean(difficulties) if difficulties else None,
        "median_block_interval_seconds": (
            statistics.median(intervals) if intervals else None
        ),
        "mean_non_coinbase_transactions_per_block": (
            statistics.fmean(transactions) if transactions else None
        ),
        "median_total_fee_per_block_base_units": (
            statistics.median(fees) if fees else None
        ),
        "mean_total_fee_per_block_base_units": (
            statistics.fmean(fees) if fees else None
        ),
        "mean_miner_revenue_rin_per_block": (
            float(statistics.fmean(revenue_rin)) if revenue_rin else None
        ),
        "mean_miner_revenue_usd_per_block": (
            statistics.fmean(revenue_usd) if revenue_usd else None
        ),
        "usd_price_coverage_pct": (
            100 * len(revenue_usd) / len(rows) if rows else 0
        ),
    }


def price_return(
    prices: dict[date, dict[str, Any]], start: date, end: date, key: str
) -> Decimal | None:
    first = prices.get(start, {}).get(key)
    last = prices.get(end, {}).get(key)
    if first in (None, D(0)) or last is None:
        return None
    return last / first - D(1)


def event_confidence(
    event_height: int,
    prices: dict[date, dict[str, Any]],
    event_day: date,
    days: int,
) -> tuple[str, str]:
    anchors = [
        prices.get(event_day - timedelta(days=days), {}).get("rin_usd"),
        prices.get(event_day, {}).get("rin_usd"),
        prices.get(event_day + timedelta(days=days), {}).get("rin_usd"),
    ]
    if any(value is None for value in anchors):
        return "unusable", "one or more event-window anchor prices are missing"
    volumes = [
        prices.get(day, {}).get("volume_usd")
        for day in daterange(
            event_day - timedelta(days=days), event_day + timedelta(days=days)
        )
    ]
    observed = [value for value in volumes if value is not None]
    if not observed:
        return "unusable", "no reported volume observations"
    if statistics.median(observed) <= D("100"):
        return (
            "low",
            "reported volume is thin and historical spread/depth is unavailable",
        )
    return (
        "low",
        "historical spread/depth and venue-level trade counts are unavailable",
    )


def export_halving_events(
    root: Path,
    halving_blocks: list[dict[str, Any]],
    chain_rows: list[dict[str, Any]],
    event_times: dict[int, int],
    prices: dict[date, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact_rows: list[dict[str, Any]] = []
    study_rows: list[dict[str, Any]] = []
    for block in halving_blocks:
        height = int(block["height"])
        event_time = event_times[height]
        old_subsidy, new_subsidy = HALVING_SUBSIDIES[height]
        exact_rows.append(
            {
                "height": height,
                "block_hash": block["hash"],
                "timestamp_unix": event_time,
                "timestamp_utc": unix_to_utc(event_time),
                "difficulty": fmt(D(str(block["header"]["difficulty"])), 12),
                "old_maximum_subsidy_rin": fmt(old_subsidy),
                "new_maximum_subsidy_rin": fmt(new_subsidy),
                "required_price_multiplier_for_nominal_subsidy_revenue": fmt(
                    old_subsidy / new_subsidy, 8
                ),
                "required_price_growth_pct": fmt(
                    (old_subsidy / new_subsidy - D(1)) * D(100), 8
                ),
                "evidence_class": "directly observed from the local synchronized node",
            }
        )
        event_day = utc_date(event_time)
        for days in (1, 7, 30):
            pre_rows = window_rows(chain_rows, height, event_time, days, "pre")
            post_rows = window_rows(chain_rows, height, event_time, days, "post")
            pre = aggregate_chain_window(pre_rows, prices)
            post = aggregate_chain_window(post_rows, prices)
            confidence, reason = event_confidence(height, prices, event_day, days)
            revenue_change = None
            hashrate_change = None
            if (
                pre["mean_miner_revenue_usd_per_block"] not in (None, 0)
                and post["mean_miner_revenue_usd_per_block"] is not None
            ):
                revenue_change = (
                    D(str(post["mean_miner_revenue_usd_per_block"]))
                    / D(str(pre["mean_miner_revenue_usd_per_block"]))
                    - D(1)
                )
            if (
                pre["median_hashrate_mhps"] not in (None, 0)
                and post["median_hashrate_mhps"] is not None
            ):
                hashrate_change = (
                    D(str(post["median_hashrate_mhps"]))
                    / D(str(pre["median_hashrate_mhps"]))
                    - D(1)
                )
            elasticity = None
            elasticity_status = (
                "not estimated: market data are low-confidence or unusable"
            )
            if confidence in {"high", "medium"} and revenue_change not in (None, D(0)):
                elasticity = hashrate_change / revenue_change
                elasticity_status = "descriptive point estimate; no causal identification"
            if height == 210_000:
                interpretability = "materially confounded"
                confounder = (
                    "operator-supplied Exbitron interruption window overlaps the event"
                )
            elif height == 420_000:
                interpretability = "not economically interpretable"
                confounder = "CoinPaprika has a material RIN-price gap around the event"
            else:
                interpretability = "materially confounded"
                confounder = (
                    "thin market and overlapping exchange/project events prevent attribution"
                )
            study_rows.append(
                {
                    "halving_height": height,
                    "event_timestamp_utc": unix_to_utc(event_time),
                    "window_days": days,
                    "pre_blocks": pre["blocks"],
                    "post_blocks": post["blocks"],
                    "pre_median_hashrate_mhps": fmt_optional(
                        pre["median_hashrate_mhps"], 8
                    ),
                    "post_median_hashrate_mhps": fmt_optional(
                        post["median_hashrate_mhps"], 8
                    ),
                    "hashrate_change_pct": fmt_optional(
                        hashrate_change * D(100) if hashrate_change is not None else None,
                        8,
                    ),
                    "pre_mean_difficulty": fmt_optional(pre["mean_difficulty"], 12),
                    "post_mean_difficulty": fmt_optional(post["mean_difficulty"], 12),
                    "pre_median_block_interval_seconds": fmt_optional(
                        pre["median_block_interval_seconds"], 4
                    ),
                    "post_median_block_interval_seconds": fmt_optional(
                        post["median_block_interval_seconds"], 4
                    ),
                    "pre_mean_non_coinbase_transactions_per_block": fmt_optional(
                        pre["mean_non_coinbase_transactions_per_block"], 8
                    ),
                    "post_mean_non_coinbase_transactions_per_block": fmt_optional(
                        post["mean_non_coinbase_transactions_per_block"], 8
                    ),
                    "pre_mean_total_fee_per_block_base_units": fmt_optional(
                        pre["mean_total_fee_per_block_base_units"], 4
                    ),
                    "post_mean_total_fee_per_block_base_units": fmt_optional(
                        post["mean_total_fee_per_block_base_units"], 4
                    ),
                    "pre_mean_miner_revenue_rin_per_block": fmt_optional(
                        pre["mean_miner_revenue_rin_per_block"], 8
                    ),
                    "post_mean_miner_revenue_rin_per_block": fmt_optional(
                        post["mean_miner_revenue_rin_per_block"], 8
                    ),
                    "pre_mean_miner_revenue_usd_per_block": fmt_optional(
                        pre["mean_miner_revenue_usd_per_block"], 12
                    ),
                    "post_mean_miner_revenue_usd_per_block": fmt_optional(
                        post["mean_miner_revenue_usd_per_block"], 12
                    ),
                    "fiat_miner_revenue_change_pct": fmt_optional(
                        revenue_change * D(100) if revenue_change is not None else None,
                        8,
                    ),
                    "descriptive_hash_supply_elasticity": fmt_optional(
                        elasticity, 8
                    ),
                    "elasticity_status": elasticity_status,
                    "market_data_confidence": confidence,
                    "confidence_reason": reason,
                    "economic_interpretability": interpretability,
                    "confounder_note": confounder,
                    "evidence_class": "derived from observed chain and frozen market data",
                }
            )

    write_csv(root / "data" / f"{REVISION}exact_halving_events.csv", exact_rows)
    write_csv(
        root / "data" / f"{REVISION}halving_price_hashrate_event_study.csv",
        study_rows,
    )
    return exact_rows, study_rows


def export_price_event_windows(
    root: Path,
    snapshot_dir: Path,
    event_times: dict[int, int],
    prices: dict[date, dict[str, Any]],
) -> list[dict[str, Any]]:
    trades = parse_nestex_trades(snapshot_dir)
    trade_counts: dict[date, int] = defaultdict(int)
    for trade in trades:
        trade_counts[utc_date(int(trade["timestamp"]) // 1000)] += 1
    trade_dates = sorted(trade_counts)
    first_trade_day = trade_dates[0] if trade_dates else None
    last_trade_day = trade_dates[-1] if trade_dates else None

    def trade_count(day: date) -> str | int:
        if (
            first_trade_day is None
            or day < first_trade_day
            or day > last_trade_day
        ):
            return ""
        return trade_counts.get(day, 0)

    rows: list[dict[str, Any]] = []
    for height, timestamp in event_times.items():
        event_day = utc_date(timestamp)
        old_subsidy, new_subsidy = HALVING_SUBSIDIES[height]
        for days in (1, 7, 30, 90):
            pre_day = event_day - timedelta(days=days)
            post_day = event_day + timedelta(days=days)
            confidence, reason = event_confidence(height, prices, event_day, days)
            pre_observation = prices.get(pre_day, {})
            event_observation = prices.get(event_day, {})
            post_observation = prices.get(post_day, {})
            rows.append(
                {
                    "halving_height": height,
                    "event_date_utc": event_day.isoformat(),
                    "window_days": days,
                    "pre_date": pre_day.isoformat(),
                    "post_date": post_day.isoformat(),
                    "rin_usd_pre_to_event_return_pct": fmt_optional(
                        (
                            price_return(prices, pre_day, event_day, "rin_usd")
                            * D(100)
                            if price_return(prices, pre_day, event_day, "rin_usd")
                            is not None
                            else None
                        ),
                        8,
                    ),
                    "rin_usd_event_to_post_return_pct": fmt_optional(
                        (
                            price_return(prices, event_day, post_day, "rin_usd")
                            * D(100)
                            if price_return(prices, event_day, post_day, "rin_usd")
                            is not None
                            else None
                        ),
                        8,
                    ),
                    "rin_usd_pre_to_post_return_pct": fmt_optional(
                        (
                            price_return(prices, pre_day, post_day, "rin_usd")
                            * D(100)
                            if price_return(prices, pre_day, post_day, "rin_usd")
                            is not None
                            else None
                        ),
                        8,
                    ),
                    "rin_btc_pre_to_event_return_pct": fmt_optional(
                        (
                            price_return(prices, pre_day, event_day, "rin_btc")
                            * D(100)
                            if price_return(prices, pre_day, event_day, "rin_btc")
                            is not None
                            else None
                        ),
                        8,
                    ),
                    "rin_btc_event_to_post_return_pct": fmt_optional(
                        (
                            price_return(prices, event_day, post_day, "rin_btc")
                            * D(100)
                            if price_return(prices, event_day, post_day, "rin_btc")
                            is not None
                            else None
                        ),
                        8,
                    ),
                    "rin_btc_pre_to_post_return_pct": fmt_optional(
                        (
                            price_return(prices, pre_day, post_day, "rin_btc")
                            * D(100)
                            if price_return(prices, pre_day, post_day, "rin_btc")
                            is not None
                            else None
                        ),
                        8,
                    ),
                    "pre_reported_volume_24h_usd": fmt_optional(
                        pre_observation.get("volume_usd"), 8
                    ),
                    "event_reported_volume_24h_usd": fmt_optional(
                        event_observation.get("volume_usd"), 8
                    ),
                    "post_reported_volume_24h_usd": fmt_optional(
                        post_observation.get("volume_usd"), 8
                    ),
                    "pre_nestex_executed_trade_count_if_covered": trade_count(
                        pre_day
                    ),
                    "event_nestex_executed_trade_count_if_covered": trade_count(
                        event_day
                    ),
                    "post_nestex_executed_trade_count_if_covered": trade_count(
                        post_day
                    ),
                    "historical_bid_ask_spread": "unavailable",
                    "historical_orderbook_depth": "unavailable",
                    "event_days_since_last_reported_volume_at_least_100_usd": (
                        event_observation.get(
                            "days_since_last_reported_volume_at_least_100_usd",
                            "",
                        )
                    ),
                    "displayed_price_may_be_stale": str(
                        event_observation.get("volume_usd") in (None, D(0))
                        or trade_count(event_day) in ("", 0)
                    ).lower(),
                    "required_price_multiplier": fmt(old_subsidy / new_subsidy, 8),
                    "required_price_growth_pct": fmt(
                        (old_subsidy / new_subsidy - D(1)) * D(100), 8
                    ),
                    "market_data_confidence": confidence,
                    "confidence_reason": reason,
                    "interpolation_used": "false",
                    "evidence_class": "derived from frozen observed daily ticks",
                }
            )
    write_csv(root / "data" / f"{REVISION}halving_price_event_windows.csv", rows)
    return rows


def export_price_compensation(root: Path) -> list[dict[str, Any]]:
    boundaries = read_csv(root / "data" / f"{REVISION}reward_boundary_shocks.csv")
    rows: list[dict[str, Any]] = []
    for row in boundaries:
        old = D(row["subsidy_before_rin"])
        new = D(row["subsidy_after_rin"])
        multiplier = old / new if new > 0 else None
        growth = multiplier - D(1) if multiplier is not None else None
        rows.append(
            {
                "scenario_id": row["scenario_id"],
                "scenario_display_id": row["scenario_display_id"],
                "scenario_name": row["scenario_name"],
                "boundary_height": row["boundary_height"],
                "boundary_type": row["boundary_type"],
                "old_subsidy_rin": fmt(old),
                "new_subsidy_rin": fmt(new),
                "required_price_multiplier": (
                    "undefined (new subsidy is zero)"
                    if multiplier is None
                    else fmt(multiplier, 8)
                ),
                "required_price_growth_pct": (
                    "undefined (new subsidy is zero)"
                    if growth is None
                    else fmt(growth * D(100), 8)
                ),
                "interpretation": (
                    "price-only compensation; fees and miner costs held constant"
                ),
                "evidence_class": "consensus-deterministic",
            }
        )
    write_csv(root / "data" / f"{REVISION}price_compensation.csv", rows)
    return rows


def export_market_timeline(root: Path) -> list[dict[str, Any]]:
    rows = [
        {
            "date_or_window": "2025-04-23",
            "event": "Exbitron RIN/USDT listing announcement",
            "source_url": "https://bitcointalk.org/index.php?topic=5537764",
            "evidence_class": "directly observed from a public forum source",
            "confidence": "medium",
            "notes": "Public announcement date; immutable archive still desirable.",
        },
        {
            "date_or_window": "2025-06-02",
            "event": "CoinPaprika RIN market-data listing announcement",
            "source_url": "https://bitcointalk.org/index.php?topic=5537764",
            "evidence_class": "directly observed from a public forum source",
            "confidence": "medium",
            "notes": "Public announcement date; immutable archive still desirable.",
        },
        {
            "date_or_window": "summer 2025",
            "event": "Reported Exbitron operational interruption or security incident",
            "source_url": "",
            "evidence_class": "operator-supplied evidence",
            "confidence": "low",
            "notes": "Exact date and independent primary source remain unavailable.",
        },
        {
            "date_or_window": "2025-08-20T01:52:39Z",
            "event": "First Rincoin binary subsidy halving, block 210,000",
            "source_url": "local synchronized Rincoin Core node",
            "evidence_class": "directly observed",
            "confidence": "high",
            "notes": "Exact main-chain block timestamp.",
        },
        {
            "date_or_window": "late 2025 to early 2026",
            "event": "Reported transfer of primary RIN trading activity from Exbitron to NestEx",
            "source_url": "",
            "evidence_class": "operator-supplied evidence",
            "confidence": "low",
            "notes": "Venue-level historical volume series is incomplete.",
        },
        {
            "date_or_window": "2025-12-19",
            "event": "Public takologi/rincoin repository created",
            "source_url": "https://github.com/takologi/rincoin",
            "evidence_class": "directly observed from frozen GitHub API metadata",
            "confidence": "high",
            "notes": "Repository creation is not evidence of network adoption.",
        },
        {
            "date_or_window": "2026-01-21T15:54:35Z",
            "event": "Second Rincoin binary subsidy halving, block 420,000",
            "source_url": "local synchronized Rincoin Core node",
            "evidence_class": "directly observed",
            "confidence": "high",
            "notes": "Exact main-chain block timestamp.",
        },
        {
            "date_or_window": "spring 2026",
            "event": "Reported permanent end of RIN trading on Exbitron",
            "source_url": "https://www.exbitron.com/",
            "evidence_class": "operator-supplied evidence",
            "confidence": "low",
            "notes": "The current shutdown page was unavailable to the collector; exact RIN delisting date remains unverified.",
        },
        {
            "date_or_window": "2026-04-22",
            "event": "Governance-document repository first published",
            "source_url": "https://github.com/Aevust/rincoin-rips/commit/596bfa9f0d91b2dda3517540d320231c78798d8a",
            "evidence_class": "directly observed from frozen GitHub API metadata",
            "confidence": "high",
            "notes": "Descriptive event marker only; no price causality is inferred.",
        },
        {
            "date_or_window": "2026-05-11",
            "event": "Governance-document set expanded",
            "source_url": "https://github.com/Aevust/rincoin-rips/commit/ac3d4933a901404cc121ff10ee35be27644ce77c",
            "evidence_class": "directly observed from frozen GitHub API metadata",
            "confidence": "high",
            "notes": "Descriptive event marker only.",
        },
        {
            "date_or_window": "2026-05-17",
            "event": "Rincoin Community Core maintenance work publicly committed",
            "source_url": "https://github.com/takologi/rincoin/commit/0f2d7d8b6e8feec1f7986d25eb9bccbc3f4088d1",
            "evidence_class": "directly observed from frozen GitHub API metadata",
            "confidence": "high",
            "notes": "Public code milestone; not a measure of operator adoption.",
        },
        {
            "date_or_window": "2026-05-21 to 2026-05-22",
            "event": "Governance, fork-status and canonical-source documents expanded",
            "source_url": "https://github.com/Aevust/rincoin-rips/commits/master",
            "evidence_class": "directly observed from frozen GitHub API metadata",
            "confidence": "high",
            "notes": "Descriptive labels only; no causal price interpretation.",
        },
        {
            "date_or_window": "2026-06-24T21:32:43Z",
            "event": "Third Rincoin binary subsidy halving, block 630,000",
            "source_url": "local synchronized Rincoin Core node",
            "evidence_class": "directly observed",
            "confidence": "high",
            "notes": "Exact main-chain block timestamp.",
        },
        {
            "date_or_window": "2026-07-27",
            "event": "NestEx is the dominant CoinPaprika-reported RIN venue; Rabid Rabbit and AtomicDEX/Gleec activity is small",
            "source_url": "https://api.coinpaprika.com/v1/coins/rin-rincoin/markets?quotes=USD",
            "evidence_class": "directly observed from a frozen public source",
            "confidence": "medium",
            "notes": "A dated market snapshot, not a permanent venue ranking.",
        },
    ]
    write_csv(root / "data" / f"{REVISION}market_event_timeline.csv", rows)
    return rows


def parse_nestex_liquidity(payload: str) -> dict[str, Any]:
    def capture(pattern: str) -> str:
        match = re.search(pattern, payload, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError(f"NestEx liquidity field not found: {pattern}")
        return html.unescape(match.group(1)).replace(",", "").strip()

    shares = [
        D(value)
        for value in re.findall(
            r'<td class="text-end">([0-9.]+)%</td>', payload, flags=re.IGNORECASE
        )
    ]
    provider_values = [
        D(value.replace(",", ""))
        for value in re.findall(
            r'<td class="text-end">([0-9,.]+)</td>\s*'
            r'<td class="text-end">[0-9.]+%</td>',
            payload,
            flags=re.IGNORECASE,
        )
    ]
    return {
        "liquidity_score": D(
            capture(r"RIN Liquidity Score:.*?<span[^>]*>\s*([0-9.]+)")
        ),
        "total_liquidity_usd": D(capture(r"Total Liquidity</td>\s*<td[^>]*>\$([0-9,.]+)")),
        "pooled_rin": D(capture(r"Pooled RIN</td>\s*<td[^>]*>([0-9,.]+)")),
        "pooled_usdt": D(capture(r"Pooled USDT</td>\s*<td[^>]*>([0-9,.]+)")),
        "pool_growth": D(capture(r"Pool Growth</td>\s*<td[^>]*>([0-9,.]+)")),
        "effective_price": D(capture(r"Effective Price</td>\s*<td[^>]*>([0-9,.]+)")),
        "shares_pct": shares,
        "provider_values_usdt": provider_values,
    }


def parse_nestex_trades(snapshot_dir: Path) -> list[dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for path in sorted((snapshot_dir / "nestex_tradebook").glob("page_*.json")):
        payload = read_json(path)
        for row in payload["data"]:
            indexed[int(row["trade_id"])] = row
    return sorted(indexed.values(), key=lambda row: int(row["timestamp"]))


def export_nestex_market(
    root: Path,
    snapshot_dir: Path,
    manifest: dict[str, Any],
    market_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    endpoint = parse_nestex_liquidity(
        (snapshot_dir / "nestex_rin_liquidity.html").read_text(encoding="utf-8")
    )
    endpoint_source = manifest_entry(manifest, "nestex_rin_liquidity.html")
    ticker = read_json(snapshot_dir / "nestex_rin_usdt_ticker.json")
    book = read_json(snapshot_dir / "nestex_rin_usdt_orderbook.json")
    trades = parse_nestex_trades(snapshot_dir)
    best_bid = max(D(str(value)) for value in book["bids"])
    best_ask = min(D(str(value)) for value in book["asks"])
    mid = (best_bid + best_ask) / D(2)
    spread_pct = (best_ask - best_bid) / mid * D(100)
    bid_depth = {
        pct: sum(
            D(str(quantity))
            for price, quantity in book["bids"].items()
            if D(str(price)) >= best_bid * (D(1) - D(pct) / D(100))
        )
        for pct in (1, 5, 10)
    }
    ask_depth = {
        pct: sum(
            D(str(quantity))
            for price, quantity in book["asks"].items()
            if D(str(price)) <= best_ask * (D(1) + D(pct) / D(100))
        )
        for pct in (1, 5, 10)
    }
    daily_issuance = D("9000")
    current_volume_rin = D(str(ticker["base_volume"]))
    current_volume_usdt = D(str(ticker["target_volume"]))

    snapshots = [
        {
            "snapshot": "operator-supplied screenshot",
            "retrieved_or_capture_utc": market_config["operator_supplied_claims"][
                "nestex_screenshot_capture_date"
            ],
            "ui_base_quantity_label": "Pooled NEX",
            "base_quantity_displayed": "450742.4413250",
            "pooled_usdt": "296.209619",
            "total_liquidity_usd": "592.410",
            "effective_price_usdt": "0.00065716",
            "provider_count": 3,
            "largest_provider_share_pct": "84.51",
            "second_provider_share_pct": "12.03",
            "third_provider_share_pct": "3.46",
            "reported_24h_volume_rin": "67700",
            "reported_24h_volume_usdt": "44.2847730",
            "notes": (
                "The screenshot labels the quantity Pooled NEX; NEX is NestEx's "
                "own commodity coin. The label is retained verbatim."
            ),
            "evidence_class": "operator-supplied evidence",
        },
        {
            "snapshot": "public RIN liquidity endpoint",
            "retrieved_or_capture_utc": endpoint_source["retrieved_utc"],
            "ui_base_quantity_label": "Pooled RIN",
            "base_quantity_displayed": fmt(endpoint["pooled_rin"], 6),
            "pooled_usdt": fmt(endpoint["pooled_usdt"], 6),
            "total_liquidity_usd": fmt(endpoint["total_liquidity_usd"], 2),
            "effective_price_usdt": fmt(endpoint["effective_price"], 8),
            "provider_count": len(endpoint["shares_pct"]),
            "largest_provider_share_pct": fmt(endpoint["shares_pct"][0], 2),
            "second_provider_share_pct": fmt(endpoint["shares_pct"][1], 2),
            "third_provider_share_pct": fmt(endpoint["shares_pct"][2], 2),
            "reported_24h_volume_rin": fmt(current_volume_rin, 8),
            "reported_24h_volume_usdt": fmt(current_volume_usdt, 8),
            "notes": (
                "The current endpoint explicitly labels a near-identical base "
                "quantity as Pooled RIN; this supports, but does not rewrite, "
                "the historical screenshot label."
            ),
            "evidence_class": "directly observed from a frozen public source",
        },
    ]
    write_csv(root / "data" / f"{REVISION}nestex_lp_snapshot.csv", snapshots)
    write_json(
        root / "data" / f"{REVISION}nestex_lp_snapshot.json",
        {
            "operator_supplied": snapshots[0],
            "public_endpoint": snapshots[1],
            "mechanism": (
                "exchange-managed automated liquidity reserve integrated with "
                "NestEx's centralized order book"
            ),
            "mechanism_source": "https://trade.nestex.one/liquidity-is-awesome",
            "slippage_model_status": (
                "No AMM-only slippage formula is applied; executable depth is "
                "measured from the public order book."
            ),
        },
    )

    concentration: list[dict[str, Any]] = []
    hhi = sum((share / D(100)) ** 2 for share in endpoint["shares_pct"])
    for rank, (share, value) in enumerate(
        zip(endpoint["shares_pct"], endpoint["provider_values_usdt"]), start=1
    ):
        concentration.append(
            {
                "rank": rank,
                "reported_value_usdt": fmt(value, 2),
                "share_pct": fmt(share, 2),
                "hhi_contribution": fmt((share / D(100)) ** 2, 8),
                "operator_identity": (
                    "Rincoin Community (operator-supplied)"
                    if rank == 1
                    else "not independently identified"
                ),
                "evidence_class": (
                    "directly observed share; operator identity is operator-supplied"
                ),
            }
        )
    concentration.append(
        {
            "rank": "summary",
            "reported_value_usdt": fmt(endpoint["total_liquidity_usd"], 2),
            "share_pct": fmt(sum(endpoint["shares_pct"]), 2),
            "hhi_contribution": fmt(hhi, 8),
            "operator_identity": f"effective provider count {fmt(D(1) / hhi, 4)}",
            "evidence_class": "derived from observed endpoint shares",
        }
    )
    write_csv(
        root / "data" / f"{REVISION}nestex_lp_concentration.csv", concentration
    )

    daily: dict[date, dict[str, Any]] = defaultdict(
        lambda: {"trades": 0, "rin": D(0), "usdt": D(0), "first": None, "last": None}
    )
    for trade in trades:
        timestamp = int(trade["timestamp"]) // 1000
        day = utc_date(timestamp)
        quantity = D(str(trade["quantity"]))
        price = D(str(trade["price"]))
        record = daily[day]
        record["trades"] += 1
        record["rin"] += quantity
        record["usdt"] += quantity * price
        record["first"] = (
            timestamp if record["first"] is None else min(record["first"], timestamp)
        )
        record["last"] = (
            timestamp if record["last"] is None else max(record["last"], timestamp)
        )
    trade_rows = [
        {
            "date_utc": day.isoformat(),
            "executed_trade_count": record["trades"],
            "executed_volume_rin": fmt(record["rin"], 8),
            "executed_volume_usdt": fmt(record["usdt"], 8),
            "first_trade_utc": unix_to_utc(record["first"]),
            "last_trade_utc": unix_to_utc(record["last"]),
            "source": "NestEx public paginated tradebook, pages 1-60",
            "evidence_class": "directly observed from a frozen public source",
        }
        for day, record in sorted(daily.items())
    ]
    write_csv(root / "data" / f"{REVISION}nestex_trade_history.csv", trade_rows)

    observation = [
        {
            "retrieved_utc": endpoint_source["retrieved_utc"],
            "venue": "NestEx",
            "pair": "RIN/USDT",
            "best_bid": fmt(best_bid, 8),
            "best_ask": fmt(best_ask, 8),
            "spread_pct": fmt(spread_pct, 8),
            "reported_24h_volume_rin": fmt(current_volume_rin, 8),
            "reported_24h_volume_usdt": fmt(current_volume_usdt, 8),
            "bid_depth_within_1_pct_rin": fmt(bid_depth[1], 8),
            "bid_depth_within_5_pct_rin": fmt(bid_depth[5], 8),
            "bid_depth_within_10_pct_rin": fmt(bid_depth[10], 8),
            "ask_depth_within_1_pct_rin": fmt(ask_depth[1], 8),
            "ask_depth_within_5_pct_rin": fmt(ask_depth[5], 8),
            "ask_depth_within_10_pct_rin": fmt(ask_depth[10], 8),
            "lp_total_usd": fmt(endpoint["total_liquidity_usd"], 2),
            "lp_provider_count": len(endpoint["shares_pct"]),
            "lp_largest_share_pct": fmt(endpoint["shares_pct"][0], 2),
            "lp_hhi": fmt(hhi, 8),
            "lp_total_relative_to_scheduled_daily_issuance_usd": fmt(
                endpoint["total_liquidity_usd"]
                / (daily_issuance * endpoint["effective_price"]),
                8,
            ),
            "reported_volume_relative_to_scheduled_daily_issuance": fmt(
                current_volume_rin / daily_issuance, 8
            ),
            "market_data_confidence": "low",
            "notes": (
                "Thin volume; total LP capital is not treated as executable "
                "plus/minus-five-percent depth."
            ),
            "evidence_class": "directly observed and derived from observed data",
        }
    ]
    write_csv(
        root / "data" / f"{REVISION}exchange_observation_log.csv", observation
    )
    return snapshots, concentration, trade_rows


def export_sticky_hashrate(
    root: Path, market_config: dict[str, Any]
) -> list[dict[str, Any]]:
    observed = D(market_config["frozen_honest_hashrate_mh"])
    rental = D(market_config["frozen_visible_rental_capacity_mh"])
    available_rental = rental
    rows: list[dict[str, Any]] = []
    for committed_text in market_config["operator_committed_hashrate_mh"]:
        committed = D(committed_text)
        elastic = observed - committed
        if elastic < 0:
            raise ValueError("Committed hashrate exceeds observed hashrate")
        for exit_text in market_config["elastic_hash_exit_pct"]:
            exit_pct = D(exit_text)
            honest = committed + elastic * (D(1) - exit_pct / D(100))
            for owned_text in market_config["configurable_owned_hashrate_mh"]:
                owned = D(owned_text)
                attacker = available_rental + owned
                combined = honest + attacker
                rows.append(
                    {
                        "observed_pre_exit_hashrate_mh": fmt(observed, 8),
                        "operator_committed_hashrate_mh": fmt(committed, 8),
                        "committed_share_of_observed_pct": fmt(
                            committed / observed * D(100), 8
                        ),
                        "elastic_hashrate_mh": fmt(elastic, 8),
                        "elastic_exit_pct": fmt(exit_pct, 2),
                        "remaining_honest_hashrate_mh": fmt(honest, 8),
                        "visible_rental_capacity_mh": fmt(rental, 8),
                        "rental_overlap_assumption_pct": "0.00",
                        "available_rental_capacity_mh": fmt(available_rental, 8),
                        "configurable_owned_hashrate_mh": fmt(owned, 8),
                        "attacker_visible_plus_owned_hashrate_mh": fmt(attacker, 8),
                        "rental_pct_of_pre_existing_honest": fmt(
                            available_rental / honest * D(100), 8
                        )
                        if honest
                        else "undefined",
                        "attacker_pct_of_combined_hashrate": fmt(
                            attacker / combined * D(100), 8
                        )
                        if combined
                        else "undefined",
                        "visible_rental_alone_exceeds_honest": str(
                            available_rental > honest
                        ).lower(),
                        "visible_plus_owned_exceeds_honest": str(
                            attacker > honest
                        ).lower(),
                        "additional_owned_hash_required_to_exceed_honest_mh": fmt(
                            max(D(0), honest - available_rental) + D("0.00000001"),
                            8,
                        ),
                        "committed_hash_status": "operator-committed under current policy",
                        "evidence_class": (
                            "operator-supplied committed hash plus speculative stress case "
                            "and frozen observed market/network values; zero-overlap "
                            "additive rental assumption"
                        ),
                    }
                )
    write_csv(
        root / "data" / f"{REVISION}sticky_elastic_hashrate_scenarios.csv", rows
    )
    return rows


def catchup_probability(attacker_fraction: Decimal, confirmations: int) -> Decimal:
    """Biased-random-walk probability of ever catching up from z blocks behind."""
    if attacker_fraction >= D("0.5"):
        return D(1)
    honest_fraction = D(1) - attacker_fraction
    return (attacker_fraction / honest_fraction) ** confirmations


def export_rental_overlap_model(
    root: Path, market_config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observed = D(market_config["frozen_honest_hashrate_mh"])
    rental = D(market_config["frozen_visible_rental_capacity_mh"])
    committed = D(
        market_config["operator_supplied_claims"][
            "community_operated_hashrate_mh"
        ]
    )
    maximum_removable = observed - committed
    rows: list[dict[str, Any]] = []
    confirmation_rows: list[dict[str, Any]] = []

    for alpha_text in market_config["rental_overlap_fractions_pct"]:
        alpha_pct = D(alpha_text)
        alpha = alpha_pct / D(100)
        removed = rental * alpha
        if removed > maximum_removable:
            raise ValueError(
                "Rental overlap would remove operator-committed non-MRR hash"
            )
        remaining_honest = observed - removed
        attacker = rental
        combined = remaining_honest + attacker
        attacker_fraction = attacker / combined
        exceeds = attacker > remaining_honest
        rows.append(
            {
                "rental_overlap_alpha_pct": fmt(alpha_pct, 2),
                "observed_network_hashrate_mh": fmt(observed, 8),
                "operator_committed_non_mrr_hashrate_mh": fmt(committed, 8),
                "visible_rental_capacity_mh": fmt(rental, 8),
                "honest_hash_removed_by_redirection_mh": fmt(removed, 8),
                "remaining_honest_hashrate_mh": fmt(remaining_honest, 8),
                "attacker_hashrate_mh": fmt(attacker, 8),
                "combined_post_redirection_hashrate_mh": fmt(combined, 8),
                "attacker_fraction_of_combined_pct": fmt(
                    attacker_fraction * D(100), 8
                ),
                "attacker_exceeds_remaining_honest": str(exceeds).lower(),
                "evidence_class": (
                    "speculative overlap case using directly observed frozen "
                    "rental and network values; committed hash is operator-supplied"
                ),
            }
        )
        for confirmations in market_config["confirmation_depths"]:
            probability = catchup_probability(attacker_fraction, int(confirmations))
            confirmation_rows.append(
                {
                    "rental_overlap_alpha_pct": fmt(alpha_pct, 2),
                    "confirmation_depth": int(confirmations),
                    "attacker_fraction_of_combined_pct": fmt(
                        attacker_fraction * D(100), 8
                    ),
                    "biased_random_walk_eventual_catchup_probability": fmt(
                        probability, 12
                    ),
                    "attacker_exceeds_remaining_honest": str(exceeds).lower(),
                    "proxy_definition": (
                        "P=1 when q>=0.5, otherwise P=(q/(1-q))^z for an "
                        "attacker starting z blocks behind"
                    ),
                    "evidence_class": (
                        "mathematical proxy over a speculative rental-overlap case; "
                        "not an empirical reorganisation probability"
                    ),
                }
            )

    write_csv(root / "data" / "rental_overlap_model.csv", rows)
    write_csv(
        root / "data" / "rental_overlap_confirmation_proxies.csv",
        confirmation_rows,
    )
    source = (
        "data/scenario_config.json and frozen network/rental observations"
    )
    generated_include(
        root,
        "rental_overlap_model_table.qmd",
        source,
        [
            "Alpha",
            "Removed MH/s",
            "Remaining honest",
            "Attacker MH/s",
            "Attacker / combined",
            "Attacker exceeds honest",
        ],
        [
            [
                row["rental_overlap_alpha_pct"] + "%",
                row["honest_hash_removed_by_redirection_mh"],
                row["remaining_honest_hashrate_mh"],
                row["attacker_hashrate_mh"],
                row["attacker_fraction_of_combined_pct"] + "%",
                row["attacker_exceeds_remaining_honest"],
            ]
            for row in rows
        ],
        ["right", "right", "right", "right", "right", "center"],
    )
    generated_include(
        root,
        "confirmation_catchup_proxy_table.qmd",
        source,
        ["Alpha", "2 conf", "6 conf", "12 conf", "20 conf", "24 conf"],
        [
            [
                row["rental_overlap_alpha_pct"] + "%",
                *[
                    fmt(
                        D(
                            next(
                                item[
                                    "biased_random_walk_eventual_catchup_probability"
                                ]
                                for item in confirmation_rows
                                if item["rental_overlap_alpha_pct"]
                                == row["rental_overlap_alpha_pct"]
                                and int(item["confirmation_depth"]) == depth
                            )
                        )
                        * D(100),
                        6,
                    )
                    + "%"
                    for depth in market_config["confirmation_depths"]
                ],
            ]
            for row in rows
        ],
        ["right", "right", "right", "right", "right", "right"],
    )
    return rows, confirmation_rows


def export_confirmation_policies(
    root: Path, market_config: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in market_config["service_confirmation_policies"]]
    write_csv(root / "data" / "service_confirmation_policies.csv", rows)
    generated_include(
        root,
        "service_confirmation_policies_table.qmd",
        "data/scenario_config.json",
        ["Service", "Confirmations", "Policy context", "Evidence"],
        [
            [
                row["service"],
                str(row["confirmations"]),
                row["policy_type"],
                row["evidence_class"],
            ]
            for row in rows
        ],
        ["left", "right", "left", "left"],
        column_relative_widths=[20, 10, 35, 35],
    )
    return rows


def export_rental_snapshot_comparison(
    root: Path, base_snapshot: Path, market_snapshot: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, snapshot in (
        ("network-aligned base snapshot", base_snapshot),
        ("later same-day snapshot", market_snapshot),
    ):
        payload = read_json(snapshot / "mrr_rinhash_rigs.json")
        manifest = read_json(snapshot / "SOURCE_MANIFEST.json")
        source = manifest_entry(manifest, "mrr_rinhash_rigs.json")
        available = payload["data"]["stats"]["available"]
        rented = payload["data"]["stats"]["rented"]
        rows.append(
            {
                "snapshot": label,
                "retrieved_utc": source["retrieved_utc"],
                "available_rigs": int(available["rigs"]),
                "advertised_available_hashrate_mh": fmt(
                    D(str(available["hash"]["hash"])) / D(1_000_000), 8
                ),
                "rented_rigs": int(rented["rigs"]),
                "lowest_ask_btc_per_mh_day": payload["data"]["stats"]["prices"][
                    "lowest"
                ],
                "baseline_use": (
                    "used with the contemporaneous 19.70723840 MH/s node estimate"
                    if label == "network-aligned base snapshot"
                    else "reported as a later market observation; not mixed into the aligned baseline"
                ),
                "evidence_class": "directly observed from a frozen public source",
            }
        )
    write_csv(
        root / "data" / f"{REVISION}rental_snapshot_comparison.csv", rows
    )
    return rows


def export_transaction_metrics(
    root: Path, snapshot_dir: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = snapshot_dir / "node_transaction_metrics_365d.jsonl.gz"
    values: dict[str, list[float]] = defaultdict(list)
    daily: dict[date, dict[str, Any]] = defaultdict(
        lambda: {
            "transactions": 0,
            "aggregate_output": D(0),
            "bytes": 0,
            "fees": 0,
        }
    )
    transactions: list[tuple[float, int, int, int]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            output_rin = D(int(row["aggregate_output_value_base_units"])) / COIN
            input_rin = D(int(row["aggregate_input_value_base_units"])) / COIN
            fee_rin = D(int(row["fee_base_units"])) / COIN
            size = int(row["serialized_size_bytes"])
            values["aggregate_input_rin"].append(float(input_rin))
            values["aggregate_output_rin"].append(float(output_rin))
            values["serialized_size_bytes"].append(size)
            values["vsize_bytes"].append(int(row["vsize_bytes"]))
            values["input_count"].append(int(row["input_count"]))
            values["output_count"].append(int(row["output_count"]))
            values["fee_rin"].append(float(fee_rin))
            values["fee_rate_base_units_per_vbyte"].append(
                float(D(str(row["fee_rate_base_units_per_vbyte"])))
            )
            day = utc_date(int(row["time"]))
            record = daily[day]
            record["transactions"] += 1
            record["aggregate_output"] += output_rin
            record["bytes"] += size
            record["fees"] += int(row["fee_base_units"])
            transactions.append(
                (float(output_rin), size, int(row["input_count"]), int(row["output_count"]))
            )

    summary: list[dict[str, Any]] = []
    units = {
        "aggregate_input_rin": "RIN",
        "aggregate_output_rin": "RIN (includes possible change)",
        "serialized_size_bytes": "bytes",
        "vsize_bytes": "vbytes",
        "input_count": "inputs",
        "output_count": "outputs",
        "fee_rin": "RIN",
        "fee_rate_base_units_per_vbyte": "base units/vbyte",
    }
    for metric, metric_values in values.items():
        result = stats(metric_values)
        summary.append(
            {
                "metric": metric,
                "unit": units[metric],
                "observations": len(metric_values),
                "minimum": fmt(result["minimum"], 8),
                "p10": fmt(result["p10"], 8),
                "median": fmt(result["median"], 8),
                "mean": fmt(result["mean"], 8),
                "p90": fmt(result["p90"], 8),
                "maximum": fmt(result["maximum"], 8),
                "evidence_class": "derived from observed main-chain transactions",
            }
        )
    write_csv(
        root / "data" / f"{REVISION}transaction_value_size_summary.csv", summary
    )
    daily_rows = [
        {
            "date_utc": day.isoformat(),
            "non_coinbase_transactions": record["transactions"],
            "aggregate_output_rin_including_possible_change": fmt(
                record["aggregate_output"], 8
            ),
            "serialized_bytes": record["bytes"],
            "total_fees_base_units": record["fees"],
            "mean_fee_base_units_per_transaction": fmt(
                D(record["fees"]) / D(record["transactions"]), 8
            ),
            "evidence_class": "derived from observed main-chain transactions",
        }
        for day, record in sorted(daily.items())
    ]
    write_csv(
        root / "data" / f"{REVISION}transaction_value_size_by_day.csv", daily_rows
    )

    def median(items: list[float | int]) -> float:
        return statistics.median(items)

    by_structure: dict[tuple[int, int], list[tuple[float, int]]] = defaultdict(list)
    for output_value, size, inputs, outputs in transactions:
        by_structure[(inputs, outputs)].append((output_value, size))
    structure_rows = []
    for (inputs, outputs), items in sorted(
        by_structure.items(), key=lambda item: (-len(item[1]), item[0])
    )[:10]:
        sizes = [item[1] for item in items]
        output_values = [item[0] for item in items]
        structure_rows.append(
            {
                "input_count": inputs,
                "output_count": outputs,
                "observations": len(items),
                "serialized_size_p10_bytes": fmt(percentile(sizes, 0.10), 0),
                "serialized_size_median_bytes": fmt(median(sizes), 0),
                "serialized_size_p90_bytes": fmt(percentile(sizes, 0.90), 0),
                "serialized_size_maximum_bytes": max(sizes),
                "aggregate_output_value_median_rin": fmt(median(output_values), 8),
                "evidence_class": "derived structural class; no transaction purpose inferred",
            }
        )
    write_csv(
        root / "data" / f"{REVISION}transaction_size_by_structure.csv",
        structure_rows,
    )

    value_bins = [
        (None, 1.0, "less than 1 RIN"),
        (1.0, 10.0, "1 to less than 10 RIN"),
        (10.0, 100.0, "10 to less than 100 RIN"),
        (100.0, 1_000.0, "100 to less than 1,000 RIN"),
        (1_000.0, 10_000.0, "1,000 to less than 10,000 RIN"),
        (10_000.0, 100_000.0, "10,000 to less than 100,000 RIN"),
        (100_000.0, None, "100,000 RIN or more"),
    ]
    value_rows = []
    for lower, upper, label in value_bins:
        items = [
            item
            for item in transactions
            if (lower is None or item[0] >= lower)
            and (upper is None or item[0] < upper)
        ]
        sizes = [item[1] for item in items]
        inputs = [item[2] for item in items]
        outputs = [item[3] for item in items]
        value_rows.append(
            {
                "aggregate_output_value_range": label,
                "observations": len(items),
                "serialized_size_p10_bytes": fmt(percentile(sizes, 0.10), 0),
                "serialized_size_median_bytes": fmt(median(sizes), 0),
                "serialized_size_p90_bytes": fmt(percentile(sizes, 0.90), 0),
                "median_input_count": fmt(median(inputs), 0),
                "median_output_count": fmt(median(outputs), 0),
                "value_semantics": "aggregate outputs include possible change and known test activity",
            }
        )
    write_csv(
        root / "data" / f"{REVISION}transaction_size_by_value_range.csv",
        value_rows,
    )

    def ranks(items: list[float | int]) -> list[float]:
        order = sorted(range(len(items)), key=items.__getitem__)
        result = [0.0] * len(items)
        index = 0
        while index < len(order):
            end = index + 1
            while end < len(order) and items[order[end]] == items[order[index]]:
                end += 1
            rank = (index + end - 1) / 2 + 1
            for position in order[index:end]:
                result[position] = rank
            index = end
        return result

    def pearson(left: list[float | int], right: list[float | int]) -> float:
        left_mean = statistics.fmean(left)
        right_mean = statistics.fmean(right)
        numerator = sum(
            (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
        )
        denominator = math.sqrt(
            sum((x - left_mean) ** 2 for x in left)
            * sum((y - right_mean) ** 2 for y in right)
        )
        return numerator / denominator

    log_values = [math.log10(max(item[0], 0.00000001)) for item in transactions]
    sizes = [item[1] for item in transactions]
    log_sizes = [math.log10(item[1]) for item in transactions]
    total_io = [item[2] + item[3] for item in transactions]
    relationship_rows = [
        {
            "relationship": "log10 aggregate output RIN vs log10 serialized bytes",
            "measure": "Pearson correlation",
            "value": fmt(pearson(log_values, log_sizes), 8),
            "interpretation_limit": "descriptive association only; mixed structures and known test activity",
        },
        {
            "relationship": "aggregate output RIN rank vs serialized-byte rank",
            "measure": "Spearman rank correlation",
            "value": fmt(pearson(ranks(log_values), ranks(sizes)), 8),
            "interpretation_limit": "descriptive association only; aggregate outputs include possible change",
        },
        {
            "relationship": "input-plus-output count vs serialized bytes",
            "measure": "Pearson correlation",
            "value": fmt(pearson(total_io, sizes), 8),
            "interpretation_limit": "structure proxy; script and witness composition also affect size",
        },
        {
            "relationship": "input-plus-output-count rank vs serialized-byte rank",
            "measure": "Spearman rank correlation",
            "value": fmt(pearson(ranks(total_io), ranks(sizes)), 8),
            "interpretation_limit": "structure proxy; no causal estimate is claimed",
        },
    ]
    write_csv(
        root / "data" / f"{REVISION}transaction_size_relationships.csv",
        relationship_rows,
    )

    generated_include(
        root,
        f"{REVISION}transaction_size_by_structure_table.qmd",
        "scripts/analyze_market_evidence.py and frozen transaction metrics",
        ["Inputs", "Outputs", "Transactions", "Size p10", "Median size", "Size p90", "Median aggregate output"],
        [
            [
                str(row["input_count"]),
                str(row["output_count"]),
                str(row["observations"]),
                str(row["serialized_size_p10_bytes"]) + " B",
                str(row["serialized_size_median_bytes"]) + " B",
                str(row["serialized_size_p90_bytes"]) + " B",
                str(row["aggregate_output_value_median_rin"]) + " RIN",
            ]
            for row in structure_rows
        ],
        ["right", "right", "right", "right", "right", "right", "right"],
        column_relative_widths=[9, 9, 14, 14, 14, 14, 26]
    )
    generated_include(
        root,
        f"{REVISION}transaction_size_by_value_range_table.qmd",
        "scripts/analyze_market_evidence.py and frozen transaction metrics",
        ["Aggregate-output range", "Transactions", "Size p10", "Median size", "Size p90", "Median inputs", "Median outputs"],
        [
            [
                str(row["aggregate_output_value_range"]),
                str(row["observations"]),
                str(row["serialized_size_p10_bytes"]) + " B",
                str(row["serialized_size_median_bytes"]) + " B",
                str(row["serialized_size_p90_bytes"]) + " B",
                str(row["median_input_count"]),
                str(row["median_output_count"]),
            ]
            for row in value_rows
        ],
        ["left", "right", "right", "right", "right", "right", "right"],
    )
    generated_include(
        root,
        f"{REVISION}transaction_size_relationships_table.qmd",
        "scripts/analyze_market_evidence.py and frozen transaction metrics",
        ["Variables", "Measure", "Value", "Limit"],
        [
            [
                str(row["relationship"]),
                str(row["measure"]),
                str(row["value"]),
                str(row["interpretation_limit"]),
            ]
            for row in relationship_rows
        ],
        ["left", "left", "right", "left"],
        column_relative_widths=[30, 20, 20, 30]
    )
    return summary, daily_rows


def export_shock_summary(root: Path) -> list[dict[str, Any]]:
    boundaries = read_csv(root / "data" / f"{REVISION}reward_boundary_shocks.csv")
    metrics = {
        row["scenario_id"]: row
        for row in read_csv(root / "data" / f"{REVISION}reward_shock_metrics.csv")
    }
    summaries = {
        row["scenario_id"]: row
        for row in read_csv(root / "data" / f"{REVISION}scenario_summary.csv")
    }
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in boundaries:
        grouped[row["scenario_id"]].append(row)
    rows: list[dict[str, Any]] = []
    for scenario_id, scenario_boundaries in grouped.items():
        activation = next(
            row for row in scenario_boundaries if row["boundary_type"] == "activation"
        )
        first_later = min(
            (
                row
                for row in scenario_boundaries
                if row["boundary_type"] != "activation"
            ),
            key=lambda row: int(row["boundary_height"]),
        )
        summary = summaries[scenario_id]
        metric = metrics[scenario_id]
        cadence = "configured phase boundaries"
        if scenario_id in {"S0"}:
            cadence = "210,000-block binary integer halvings"
        elif scenario_id in {"S1", "S2a", "S2b", "S3"}:
            cadence = "210,000-block recursive 19/20 reductions"
        elif scenario_id == "S4":
            cadence = "210,000-block 113/114 reductions"
        elif scenario_id in {"S5a", "S5B"}:
            cadence = "2,100,000-block binary integer halvings"
        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_display_id": summary["scenario_display_id"],
                "scenario_name": activation["scenario_name"],
                "activation_old_subsidy_rin": activation["subsidy_before_rin"],
                "activation_new_subsidy_rin": activation["subsidy_after_rin"],
                "immediate_miner_revenue_shock_pct": fmt(
                    abs(D(activation["nominal_revenue_shock_pct"])), 8
                ),
                "activation_required_price_growth_pct": fmt(
                    (
                        D(activation["subsidy_before_rin"])
                        / D(activation["subsidy_after_rin"])
                        - D(1)
                    )
                    * D(100),
                    8,
                ),
                "normal_scheduled_reduction_rate": metric[
                    "normal_scheduled_reduction_rate"
                ],
                "first_later_reward_shock_height": first_later["boundary_height"],
                "first_later_reward_shock_pct": fmt(
                    abs(D(first_later["nominal_revenue_shock_pct"])), 8
                ),
                "largest_later_reduction_at_or_above_1_rin": metric[
                    "largest_later_reduction_at_or_above_1_rin"
                ],
                "largest_later_reduction_at_or_above_0_1_rin": metric[
                    "largest_later_reduction_at_or_above_0_1_rin"
                ],
                "largest_later_reduction_at_or_above_0_01_rin": metric[
                    "largest_later_reduction_at_or_above_0_01_rin"
                ],
                "terminal_integer_rounding_height": metric[
                    "terminal_integer_rounding_height"
                ],
                "terminal_pre_boundary_subsidy_rin": metric[
                    "terminal_pre_boundary_subsidy_rin"
                ],
                "terminal_transition_type": metric["terminal_transition_type"],
                "terminal_transition_shock": metric[
                    "terminal_transition_shock"
                ],
                "terminal_integer_rounding_shock": metric[
                    "terminal_integer_rounding_shock"
                ],
                "reduction_cadence": cadence,
                "first_height_below_1_rin": summary["first_height_below_1_rin"],
                "first_height_below_0_5_rin": summary[
                    "first_height_below_0_5_rin"
                ],
                "constant_phase_start_height": summary[
                    "constant_phase_start_height"
                ],
                "constant_phase_end_height": summary["constant_phase_end_height"],
                "constant_phase_subsidy_rin": summary[
                    "constant_phase_subsidy_rin_display"
                ],
                "first_zero_subsidy_height": summary["first_zero_subsidy_height"],
                "unbounded": summary["unbounded"],
                "eventual_fee_dependence": (
                    "fees become sole scheduled miner revenue after zero subsidy"
                    if summary["first_zero_subsidy_height"]
                    else "nominal subsidy remains under the configured tail/plot model"
                ),
                "evidence_class": "consensus-deterministic",
            }
        )
    write_csv(
        root / "data" / f"{REVISION}activation_terminal_shock_comparison.csv",
        rows,
    )
    return rows


def export_literature_review(root: Path) -> list[dict[str, Any]]:
    rows = [
        {
            "topic": "reward and hash-supply elasticity",
            "source": "Kawaguchi, Komiyama and Noda (2026), Miners' Reward Elasticity and Stability of Competing Proof-of-Work Cryptocurrencies",
            "citation_key": "kawaguchi2026reward",
            "url": "https://doi.org/10.1111/iere.70060",
            "source_type": "peer-reviewed primary research",
            "relevance": "Identifies reward elasticity from SHA-256 halving events and models competing-chain DAA stability.",
            "transfer_limit": "BTC/BCH/BSV estimates cannot be transplanted to RinHash.",
        },
        {
            "topic": "price-driven multi-chain hash allocation",
            "source": "Bissias, Levine and Thibodeau (2018), Using Economic Risk to Model Miner Hash Rate Allocation in Cryptocurrencies",
            "citation_key": "bissias2018allocation",
            "url": "https://arxiv.org/abs/1806.07189",
            "source_type": "technical research paper",
            "relevance": "Models allocation across compatible PoW chains using price and miner risk.",
            "transfer_limit": "RinHash market depth and miner choices differ from SHA-256 markets.",
        },
        {
            "topic": "difficulty-adjustment instability",
            "source": "Ilie, Werner, Stewart and Knottenbelt (2020), Unstable Throughput: When the Difficulty Algorithm Breaks",
            "citation_key": "ilie2020unstable",
            "url": "https://arxiv.org/abs/2006.03044",
            "source_type": "empirical and simulation research",
            "relevance": "Shows how miner switching and DAA feedback can destabilize block throughput.",
            "transfer_limit": "The studied BCH DAA is not Rincoin's DGWv3.",
        },
        {
            "topic": "fee-only mining security",
            "source": "Carlsten, Kalodner, Weinberg and Narayanan (2016), On the Instability of Bitcoin Without the Block Reward",
            "citation_key": "carlsten2016instability",
            "url": "https://www.cs.princeton.edu/~arvindn/publications/mining_CCS.pdf",
            "source_type": "peer-reviewed security research",
            "relevance": "Analyzes strategic instability when fees dominate miner rewards.",
            "transfer_limit": "Bitcoin fee demand and block timing are not Rincoin observations.",
        },
        {
            "topic": "fee-market economics",
            "source": "Easley, O'Hara and Basu (2019), From Mining to Markets: The Evolution of Bitcoin Transaction Fees",
            "citation_key": "easley2019fees",
            "url": "https://doi.org/10.1016/j.jfineco.2019.03.004",
            "source_type": "peer-reviewed economic research",
            "relevance": "Models miner/user incentives and the emergence of transaction fees.",
            "transfer_limit": "Bitcoin usage and liquidity are materially different.",
        },
        {
            "topic": "majority-attack economics",
            "source": "Budish (2018), The Economic Limits of Bitcoin and the Blockchain",
            "citation_key": "budish2018limits",
            "url": "https://doi.org/10.3386/w24717",
            "source_type": "economic working paper",
            "relevance": "Separates recurring miner-security expenditure from one-off attack value.",
            "transfer_limit": "A theoretical constraint, not a Rincoin attack-cost estimate.",
        },
        {
            "topic": "PoW security and performance",
            "source": "Gervais et al. (2016), On the Security and Performance of Proof of Work Blockchains",
            "citation_key": "gervais2016security",
            "url": "https://eprint.iacr.org/2016/555",
            "source_type": "peer-reviewed security research",
            "relevance": "Formalizes security/performance trade-offs and adversarial mining parameters.",
            "transfer_limit": "Parameters require Rincoin-specific calibration.",
        },
    ]
    write_csv(root / "data" / f"{REVISION}pow_security_literature.csv", rows)
    return rows


def export_operator_concentration(root: Path) -> list[dict[str, Any]]:
    rows = [
        {
            "surface": "mining",
            "observed_or_reported_resource": "at least 4 MH/s",
            "share_or_context": "20.30% of the frozen 19.70723840 MH/s network estimate",
            "resilience_effect": "operator-committed hash remains in the modeled downside cases",
            "dependency": "network resilience becomes partly dependent on one operator's current policy",
            "evidence_class": "operator-supplied evidence plus derived ratio",
        },
        {
            "surface": "NestEx liquidity",
            "observed_or_reported_resource": "84.51% of displayed LP value",
            "share_or_context": "largest of three reported LP positions",
            "resilience_effect": "committed liquidity supports a thin market",
            "dependency": "withdrawal or repricing by one provider can materially change liquidity",
            "evidence_class": "observed share; operator identity is operator-supplied",
        },
        {
            "surface": "Fulcrum and related infrastructure",
            "observed_or_reported_resource": "community-operated services",
            "share_or_context": "independent operator count not established",
            "resilience_effect": "services provide usable network access",
            "dependency": "services controlled by one operator are not independent redundancy",
            "evidence_class": "operator-supplied evidence",
        },
    ]
    write_csv(root / "data" / f"{REVISION}cross_layer_operator_concentration.csv", rows)
    return rows


def export_figures(
    root: Path,
    price_rows: list[dict[str, Any]],
    event_times: dict[int, int],
    chain_rows: list[dict[str, Any]],
    price_windows: list[dict[str, Any]],
    sticky_rows: list[dict[str, Any]],
    concentration: list[dict[str, Any]],
    shock_rows: list[dict[str, Any]],
) -> None:
    figures = root / "figures"
    origin = date.fromisoformat(price_rows[0]["date_utc"])
    price_points = [
        (
            (date.fromisoformat(row["date_utc"]) - origin).days,
            float(row["rin_usd_historical_tick"]),
        )
        for row in price_rows
        if row["rin_usd_historical_tick"]
    ]
    volume_points = [
        (
            (date.fromisoformat(row["date_utc"]) - origin).days,
            float(row["reported_volume_24h_usd"]),
        )
        for row in price_rows
        if row["reported_volume_24h_usd"]
    ]
    base.draw_line_chart(
        figures / f"{REVISION}rin_usd_history.png",
        "RIN/USD daily historical ticks (CoinPaprika frozen snapshot)",
        f"Days after {origin.isoformat()}",
        "USD per RIN",
        [("RIN/USD historical tick", base.COLORS["blue"], price_points)],
    )
    price_chart = figures / f"{REVISION}rin_usd_history.png"
    image = Image.open(price_chart)
    draw = ImageDraw.Draw(image)
    try:
        marker_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13
        )
    except OSError:
        marker_font = ImageFont.load_default()
    plot_left = 145
    plot_width = 1800 - 145 - 420
    plot_top = 100
    plot_bottom = 930 - 120
    max_day = (date.fromisoformat(price_rows[-1]["date_utc"]) - origin).days
    markers = [
        (date(2025, 8, 20), "H210k"),
        (date(2025, 12, 19), "community repo"),
        (date(2026, 1, 21), "H420k"),
        (date(2026, 4, 22), "governance docs"),
        (date(2026, 5, 17), "community core"),
        (date(2026, 6, 24), "H630k"),
    ]
    for index, (marker_day, label) in enumerate(markers):
        offset = (marker_day - origin).days
        if not 0 <= offset <= max_day:
            continue
        x = plot_left + offset / max_day * plot_width
        for y in range(plot_top, plot_bottom, 10):
            draw.line((x, y, x, min(y + 5, plot_bottom)), fill=(110, 110, 110))
        draw.text(
            (x + 3, plot_top + 5 + (index % 3) * 18),
            label,
            fill=(65, 65, 65),
            font=marker_font,
        )
    image.save(price_chart)
    base.draw_line_chart(
        figures / f"{REVISION}rin_reported_volume_history.png",
        "RIN reported 24-hour volume (CoinPaprika frozen snapshot)",
        f"Days after {origin.isoformat()}",
        "Reported USD volume",
        [("Reported volume", base.COLORS["orange"], volume_points)],
    )

    hash_series = []
    for height, timestamp in sorted(event_times.items()):
        points = [
            (
                float(D(int(row["time_unix"]) - timestamp) / D(SECONDS_PER_DAY)),
                float(row["rolling_120_block_hashrate_mhps"]),
            )
            for row in chain_rows
            if int(row["halving_height"]) == height
            and row["rolling_120_block_hashrate_mhps"] != ""
            and abs(float(row["days_from_halving"])) <= 30
        ]
        color = {
            210_000: base.COLORS["blue"],
            420_000: base.COLORS["orange"],
            630_000: base.COLORS["green"],
        }[height]
        hash_series.append((f"Block {height:,}", color, points))
    base.draw_line_chart(
        figures / f"{REVISION}halving_hashrate_windows.png",
        "Observed 120-block rolling hashrate around Rincoin halvings",
        "Days from halving",
        "MH/s",
        hash_series,
    )

    revenue_series = []
    price_index = {
        date.fromisoformat(row["date_utc"]): (
            D(row["rin_usd_historical_tick"])
            if row["rin_usd_historical_tick"]
            else None
        )
        for row in price_rows
    }
    for height, timestamp in sorted(event_times.items()):
        event_day = utc_date(timestamp)
        old, new = HALVING_SUBSIDIES[height]
        points = []
        for offset in range(-30, 31):
            day = event_day + timedelta(days=offset)
            price = price_index.get(day)
            event_price = price_index.get(event_day)
            if price is None or event_price in (None, D(0)):
                continue
            subsidy = old if offset < 0 else new
            points.append((offset, float(subsidy * price / (old * event_price) * D(100))))
        if points:
            color = {
                210_000: base.COLORS["blue"],
                420_000: base.COLORS["orange"],
                630_000: base.COLORS["green"],
            }[height]
            revenue_series.append((f"Block {height:,}", color, points))
    base.draw_line_chart(
        figures / f"{REVISION}price_compensated_halving_revenue.png",
        "Price-adjusted nominal subsidy revenue around historical halvings",
        "Days from halving",
        "Index: pre-halving subsidy at event-day price = 100",
        revenue_series,
    )

    activation_labels = [row["scenario_display_id"] for row in shock_rows]
    activation_values = [
        float(row["activation_required_price_growth_pct"]) for row in shock_rows
    ]
    base.draw_bar_chart(
        figures / f"{REVISION}activation_price_compensation.png",
        "Price growth required to offset each activation subsidy cut",
        "Required price growth (%)",
        activation_labels,
        activation_values,
        base.COLORS["red"],
    )

    sticky_subset = [
        row
        for row in sticky_rows
        if row["operator_committed_hashrate_mh"] == "4.00000000"
        and row["configurable_owned_hashrate_mh"] == "0.00000000"
    ]
    base.draw_line_chart(
        figures / f"{REVISION}sticky_elastic_hashrate.png",
        "Honest hashrate after elastic-miner exit with 4 MH/s committed",
        "Elastic-hash exit (%)",
        "Remaining honest MH/s",
        [
            (
                "Remaining honest hash",
                base.COLORS["blue"],
                [
                    (
                        float(row["elastic_exit_pct"]),
                        float(row["remaining_honest_hashrate_mh"]),
                    )
                    for row in sticky_subset
                ],
            ),
            (
                "Visible rental capacity",
                base.COLORS["red"],
                [
                    (
                        float(row["elastic_exit_pct"]),
                        float(row["available_rental_capacity_mh"]),
                    )
                    for row in sticky_subset
                ],
            ),
        ],
    )

    provider_rows = [row for row in concentration if row["rank"] != "summary"]
    base.draw_bar_chart(
        figures / f"{REVISION}nestex_lp_concentration.png",
        "NestEx RIN liquidity-provider concentration",
        "Displayed share (%)",
        [f"LP {row['rank']}" for row in provider_rows],
        [float(row["share_pct"]) for row in provider_rows],
        base.COLORS["orange"],
    )

def export_includes(
    root: Path,
    price_rows: list[dict[str, Any]],
    exact_halvings: list[dict[str, Any]],
    event_study: list[dict[str, Any]],
    price_windows: list[dict[str, Any]],
    lp_snapshots: list[dict[str, Any]],
    concentration: list[dict[str, Any]],
    sticky: list[dict[str, Any]],
    tx_summary: list[dict[str, Any]],
    shocks: list[dict[str, Any]],
    literature: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    rental_snapshots: list[dict[str, Any]],
) -> None:
    source = (
        "scripts/analyze_market_evidence.py and frozen public-review evidence"
    )
    observed_price_days = sum(
        row["missing_rin_price"] == "false" for row in price_rows
    )
    low_days = sum(row["low_reported_volume"] == "true" for row in price_rows)
    generated_include(
        root,
        f"{REVISION}price_coverage_table.qmd",
        source,
        ["Measure", "Value", "Evidence class"],
        [
            ["Requested daily period", f"{price_rows[0]['date_utc']} to {price_rows[-1]['date_utc']}", "frozen source definition"],
            ["Calendar days", f"{len(price_rows):,}", "derived"],
            ["Days with RIN price", f"{observed_price_days:,}", "directly observed"],
            ["Missing RIN-price days", f"{len(price_rows) - observed_price_days:,}", "directly observed"],
            ["Low/zero-volume days", f"{low_days:,}", "derived from reported volume"],
        ],
        ["left", "right", "left"],
    )
    generated_include(
        root,
        f"{REVISION}market_confidence_criteria_table.qmd",
        source,
        ["Flag", "Explicit criteria"],
        [
            [row["flag"], row["criteria"]]
            for row in confidence_definition_rows()
        ],
        ["center", "left"],
        column_relative_widths=[15, 85]
    )
    generated_include(
        root,
        f"{REVISION}exact_halving_table.qmd",
        source,
        ["Height", "UTC timestamp", "Old RIN", "New RIN", "Required price growth"],
        [
            [
                f"{int(row['height']):,}",
                row["timestamp_utc"],
                f"{Decimal(row['old_maximum_subsidy_rin']):.2f}",
                f"{Decimal(row['new_maximum_subsidy_rin']):.2f}",
                f"{Decimal(row['required_price_growth_pct']):.0f}%",
            ]
            for row in exact_halvings
        ],
        ["right", "center", "right", "right", "right"],
        column_relative_widths=[15, 34, 18, 18, 15],
    )
    thirty_day = [row for row in event_study if int(row["window_days"]) == 30]
    generated_include(
        root,
        f"{REVISION}halving_event_study_table.qmd",
        source,
        ["Height", "Hash pre", "Hash post", "Hash change", "Block interval pre/post", "Interpretability"],
        [
            [
                f"{int(row['halving_height']):,}",
                row["pre_median_hashrate_mhps"],
                row["post_median_hashrate_mhps"],
                (f"{Decimal(row['hashrate_change_pct']):.2f}%") if row["hashrate_change_pct"] else "n/a",
                f"{Decimal(row['pre_median_block_interval_seconds']):.1f} / {Decimal(row['post_median_block_interval_seconds']):.1f} s",
                row["economic_interpretability"],
            ]
            for row in thirty_day
        ],
        ["right", "right", "right", "right", "right", "left"],
        column_relative_widths=[10, 16, 16, 10, 18, 30],
    )
    seven_day = [row for row in price_windows if int(row["window_days"]) == 7]
    generated_include(
        root,
        f"{REVISION}halving_price_response_table.qmd",
        source,
        ["Height", "Pre to event", "Event to post", "Pre to post", "Needed", "Confidence"],
        [
            [
                f"{int(row['halving_height']):,}",
                (f"{Decimal(row['rin_usd_pre_to_event_return_pct']):.4f}%")
                if row["rin_usd_pre_to_event_return_pct"]
                else "n/a",
                (f"{Decimal(row['rin_usd_event_to_post_return_pct']):.4f}%")
                if row["rin_usd_event_to_post_return_pct"]
                else "n/a",
                (f"{Decimal(row['rin_usd_pre_to_post_return_pct']):.4f}%")
                if row["rin_usd_pre_to_post_return_pct"]
                else "n/a",
                f"{Decimal(row['required_price_growth_pct']):.0f}%",
                row["market_data_confidence"],
            ]
            for row in seven_day
        ],
        ["right", "right", "right", "right", "right", "center"],
        column_relative_widths=[12, 19, 19, 19, 12, 19],
    )
    generated_include(
        root,
        f"{REVISION}market_event_timeline_table.qmd",
        source,
        ["Date/window", "Event", "Evidence", "Confidence"],
        [
            [
                row["date_or_window"],
                row["event"],
                row["evidence_class"],
                row["confidence"],
            ]
            for row in timeline
        ],
        ["left", "left", "left", "center"],
        column_relative_widths=[20, 35, 30, 15],
    )
    generated_include(
        root,
        f"{REVISION}rental_snapshot_comparison_table.qmd",
        source,
        ["Snapshot", "UTC", "Rigs", "Available MH/s", "Lowest ask", "Use"],
        [
            [
                row["snapshot"],
                row["retrieved_utc"],
                str(row["available_rigs"]),
                f"{Decimal(row['advertised_available_hashrate_mh']):.4f}",
                row["lowest_ask_btc_per_mh_day"],
                row["baseline_use"],
            ]
            for row in rental_snapshots
        ],
        ["left", "center", "right", "right", "right", "left"],
        column_relative_widths=[18, 16, 8, 14, 16, 28],
    )
    generated_include(
        root,
        f"{REVISION}nestex_lp_snapshot_table.qmd",
        source,
        ["Snapshot", "Base label/value", "USDT", "Total USD", "Largest LP", "Evidence"],
        [
            [
                row["snapshot"],
                f"{row['ui_base_quantity_label']}: {row['base_quantity_displayed']}",
                row["pooled_usdt"],
                row["total_liquidity_usd"],
                row["largest_provider_share_pct"] + "%",
                row["evidence_class"],
            ]
            for row in lp_snapshots
        ],
        ["left", "right", "right", "right", "right", "left"],
    )
    hhi = next(row for row in concentration if row["rank"] == "summary")
    generated_include(
        root,
        f"{REVISION}operator_concentration_table.qmd",
        source,
        ["Measure", "Value", "Status"],
        [
            ["Community-operated hash", "4 MH/s (20.30% of frozen network estimate)", "operator-supplied"],
            ["Largest NestEx LP share", lp_snapshots[0]["largest_provider_share_pct"] + "%", "share observed; identity operator-supplied"],
            ["NestEx LP HHI", hhi["hhi_contribution"], "derived from public endpoint"],
            ["Effective LP provider count", hhi["operator_identity"].split()[-1], "derived from public endpoint"],
        ],
        ["left", "right", "left"],
    )
    sticky_display = [
        row
        for row in sticky
        if row["operator_committed_hashrate_mh"] == "4.00000000"
        and row["configurable_owned_hashrate_mh"] == "0.00000000"
    ]
    generated_include(
        root,
        f"{REVISION}sticky_hashrate_table.qmd",
        source,
        ["Elastic exit", "Honest MH/s", "Rental / honest", "Rental / combined", "Rental exceeds honest"],
        [
            [
                row["elastic_exit_pct"] + "%",
                row["remaining_honest_hashrate_mh"],
                row["rental_pct_of_pre_existing_honest"] + "%",
                row["attacker_pct_of_combined_hashrate"] + "%",
                row["visible_rental_alone_exceeds_honest"],
            ]
            for row in sticky_display
        ],
        ["right", "right", "right", "right", "center"],
    )
    generated_include(
        root,
        f"{REVISION}activation_shock_table.qmd",
        source,
        [
            "Scenario",
            "Immediate miner-revenue shock",
            "Price growth needed",
            "Nominal ordinary reduction",
            "Cadence",
            "Terminal",
        ],
        [
            [
                row["scenario_display_id"],
                row["immediate_miner_revenue_shock_pct"] + "%",
                row["activation_required_price_growth_pct"] + "%",
                (
                    "phase-dependent"
                    if row["normal_scheduled_reduction_rate"] == "phase-dependent"
                    else (
                        f"{Decimal(row['normal_scheduled_reduction_rate'].split('%')[0]):.2f}%"
                    )
                ),
                row["reduction_cadence"],
                (
                    "unbounded tail"
                    if row["unbounded"] == "true"
                    else (
                        f"zero at {int(row['first_zero_subsidy_height']):,}"
                        if row["first_zero_subsidy_height"]
                        else "configured finite phase"
                    )
                ),
            ]
            for row in shocks
        ],
        ["center", "right", "right", "right", "left", "left"],
        column_relative_widths=[10, 16, 16, 16, 24, 18]
    )
    generated_include(
        root,
        f"{REVISION}summary_activation_shock_table.qmd",
        source,
        [
            "Scenario",
            "Immediate miner-revenue shock",
            "First later scheduled reward shock",
            "Ordinary reduction rule",
            "Terminal integer-rounding effect",
        ],
        [
            [
                row["scenario_display_id"],
                row["immediate_miner_revenue_shock_pct"] + "%",
                (
                    f"{row['first_later_reward_shock_pct']}% at height "
                    f"{int(row['first_later_reward_shock_height']):,}"
                ),
                (
                    f"{row['normal_scheduled_reduction_rate']}; "
                    f"{row['reduction_cadence']}"
                ),
                (
                    f"{row['terminal_integer_rounding_shock']} at height "
                    f"{int(row['terminal_integer_rounding_height']):,}, "
                    f"from {row['terminal_pre_boundary_subsidy_rin']} RIN"
                ),
            ]
            for row in shocks
            if row["scenario_id"] in {"S1", "S5B"}
        ],
        ["center", "right", "right", "left", "left"],
        column_relative_widths=[15, 20, 30, 35],
    )
    generated_include(
        root,
        f"{REVISION}literature_table.qmd",
        source,
        ["Topic", "Primary source", "Rincoin transfer limit"],
        [
            [
                row["topic"],
                f"{row['source']} [@{row['citation_key']}]",
                row["transfer_limit"],
            ]
            for row in literature
        ],
        ["left", "left", "left"],
    )


def validate(
    root: Path,
    price_rows: list[dict[str, Any]],
    exact_halvings: list[dict[str, Any]],
    sticky: list[dict[str, Any]],
    shocks: list[dict[str, Any]],
    rental_snapshots: list[dict[str, Any]],
    overlap_rows: list[dict[str, Any]],
    confirmation_policies: list[dict[str, Any]],
    market_snapshot: Path,
) -> None:
    exact = {int(row["height"]): row for row in exact_halvings}
    expected_times = {
        210_000: "2025-08-20T01:52:39Z",
        420_000: "2026-01-21T15:54:35Z",
        630_000: "2026-06-24T21:32:43Z",
    }
    for height, expected in expected_times.items():
        if exact[height]["timestamp_utc"] != expected:
            raise ValueError(f"Unexpected halving timestamp at {height}")
        if exact[height]["required_price_growth_pct"] != "100.00000000":
            raise ValueError(f"Binary-halving compensation mismatch at {height}")
    if not any(row["missing_rin_price"] == "true" for row in price_rows):
        raise ValueError("CoinPaprika gap unexpectedly disappeared")
    if any("interpol" in row["price_semantics"].lower() for row in price_rows):
        raise ValueError("Price history must not claim interpolation")
    four_zero = next(
        row
        for row in sticky
        if row["operator_committed_hashrate_mh"] == "4.00000000"
        and row["elastic_exit_pct"] == "0.00"
        and row["configurable_owned_hashrate_mh"] == "0.00000000"
    )
    if four_zero["remaining_honest_hashrate_mh"] != "19.70723840":
        raise ValueError("Sticky-hash baseline mismatch")
    s1 = next(row for row in shocks if row["scenario_id"] == "S1")
    if s1["activation_required_price_growth_pct"] != "5.26315789":
        raise ValueError("S1 activation compensation mismatch")
    s6a = next(row for row in shocks if row["scenario_id"] == "S6a")
    if s6a["activation_required_price_growth_pct"] != "56.25000000":
        raise ValueError("Customized-halving activation compensation mismatch")
    expected_rental_snapshots = {
        "network-aligned base snapshot": ("22", "10.34630000"),
        "later same-day snapshot": ("14", "6.65830000"),
    }
    for row in rental_snapshots:
        expected = expected_rental_snapshots.get(row["snapshot"])
        if expected is None:
            raise ValueError(f"Unexpected rental snapshot: {row['snapshot']}")
        actual = (
            str(row["available_rigs"]),
            row["advertised_available_hashrate_mh"],
        )
        if actual != expected:
            raise ValueError(
                f"Rental snapshot mismatch for {row['snapshot']}: {actual}"
            )
    if len(rental_snapshots) != len(expected_rental_snapshots):
        raise ValueError("Rental snapshot comparison is incomplete")
    if [row["rental_overlap_alpha_pct"] for row in overlap_rows] != [
        "0.00",
        "25.00",
        "50.00",
        "75.00",
        "100.00",
    ]:
        raise ValueError("Rental-overlap alpha cases are incomplete")
    if overlap_rows[0]["attacker_exceeds_remaining_honest"] != "false":
        raise ValueError("Zero-overlap case must remain additive")
    if overlap_rows[-1]["attacker_exceeds_remaining_honest"] != "true":
        raise ValueError("Full-overlap redirection case must exceed honest hash")
    if {int(row["confirmations"]) for row in confirmation_policies} != {2, 6, 20}:
        raise ValueError("Service confirmation-policy values are incomplete")
    metadata = read_json(market_snapshot / "node_transaction_metrics_metadata.json")
    if int(metadata["transaction_records"]) != 68_946:
        raise ValueError("Transaction-metric record count mismatch")

    required = [
        f"data/{REVISION}rin_daily_price_volume.csv",
        f"data/{REVISION}exact_halving_events.csv",
        f"data/{REVISION}price_compensation.csv",
        f"data/{REVISION}market_event_timeline.csv",
        f"data/{REVISION}halving_price_hashrate_event_study.csv",
        f"data/{REVISION}rental_snapshot_comparison.csv",
        f"data/{REVISION}rental_overlap_model.csv",
        f"data/{REVISION}rental_overlap_confirmation_proxies.csv",
        f"data/{REVISION}service_confirmation_policies.csv",
        f"data/{REVISION}nestex_lp_snapshot.json",
        f"data/{REVISION}nestex_lp_concentration.csv",
        f"data/{REVISION}sticky_elastic_hashrate_scenarios.csv",
        f"data/{REVISION}transaction_value_size_summary.csv",
        f"data/{REVISION}transaction_size_by_structure.csv",
        f"data/{REVISION}transaction_size_by_value_range.csv",
        f"data/{REVISION}transaction_size_relationships.csv",
        f"data/{REVISION}activation_terminal_shock_comparison.csv",
        f"figures/{REVISION}rin_usd_history.png",
        f"figures/{REVISION}price_compensated_halving_revenue.png",
        f"figures/{REVISION}activation_price_compensation.png",
        f"includes/{REVISION}rental_snapshot_comparison_table.qmd",
        f"includes/{REVISION}rental_overlap_model_table.qmd",
        f"includes/{REVISION}confirmation_catchup_proxy_table.qmd",
        f"includes/{REVISION}service_confirmation_policies_table.qmd",
        f"includes/{REVISION}transaction_size_by_structure_table.qmd",
        f"includes/{REVISION}transaction_size_by_value_range_table.qmd",
        f"includes/{REVISION}transaction_size_relationships_table.qmd",
    ]
    for relative in required:
        path = root / relative
        if not path.exists() or path.stat().st_size == 0:
            raise ValueError(f"Missing public-review artifact: {relative}")


def main() -> None:
    root = Path.cwd()
    config = monetary.load_config(root)
    market_config = config["empirical_market_extension"]
    base_snapshot = root / config["empirical_security"]["snapshot_path"]
    market_snapshot = root / market_config["snapshot_path"]
    market_manifest_path = root / market_config["source_manifest"]
    market_manifest = read_json(market_manifest_path)
    source_rows = verify_manifest(root, market_manifest_path)
    write_csv(
        root / "data" / f"{REVISION}market_source_manifest.csv", source_rows
    )

    price_rows, prices = export_price_history(root, market_snapshot, market_config)
    halving_blocks = read_json(market_snapshot / "node_halving_blocks.json")
    chain_rows, event_times = export_halving_chain_rows(
        root, base_snapshot, market_snapshot, halving_blocks
    )
    exact_halvings, event_study = export_halving_events(
        root, halving_blocks, chain_rows, event_times, prices
    )
    price_windows = export_price_event_windows(
        root, market_snapshot, event_times, prices
    )
    export_price_compensation(root)
    timeline = export_market_timeline(root)
    lp_snapshots, concentration, _ = export_nestex_market(
        root, market_snapshot, market_manifest, market_config
    )
    rental_snapshots = export_rental_snapshot_comparison(
        root, base_snapshot, market_snapshot
    )
    sticky = export_sticky_hashrate(root, market_config)
    overlap_rows, _ = export_rental_overlap_model(root, market_config)
    confirmation_policies = export_confirmation_policies(root, market_config)
    tx_summary, _ = export_transaction_metrics(root, market_snapshot)
    shocks = export_shock_summary(root)
    literature = export_literature_review(root)
    export_operator_concentration(root)
    export_figures(
        root,
        price_rows,
        event_times,
        chain_rows,
        price_windows,
        sticky,
        concentration,
        shocks,
    )
    export_includes(
        root,
        price_rows,
        exact_halvings,
        event_study,
        price_windows,
        lp_snapshots,
        concentration,
        sticky,
        tx_summary,
        shocks,
        literature,
        timeline,
        rental_snapshots,
    )
    validate(
        root,
        price_rows,
        exact_halvings,
        sticky,
        shocks,
        rental_snapshots,
        overlap_rows,
        confirmation_policies,
        market_snapshot,
    )


if __name__ == "__main__":
    main()
