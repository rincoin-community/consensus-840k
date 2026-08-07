#!/usr/bin/env python3
"""Append one dated exchange observation for the public-review follow-up series.

Run this script once per day for 14-30 days. It freezes raw responses in a
directory-preserving snapshot and appends only source metadata to the index.
Document rendering never invokes this collector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SOURCES = {
    "nestex_ticker.json": "https://trade.nestex.one/api/cg/tickers/RIN_USDT",
    "nestex_orderbook.json": (
        "https://trade.nestex.one/api/cg/orderbook/RIN_USDT?depth=0"
    ),
    "nestex_tradebook_page_1.json": (
        "https://trade.nestex.one/api/cg/tradebook/RIN_USDT?page=1"
    ),
    "nestex_liquidity.html": (
        "https://trade.nestex.one/ajax/liq_stats.aspx?cur=RIN"
    ),
    "coinpaprika_markets.json": (
        "https://api.coinpaprika.com/v1/coins/rin-rincoin/markets?quotes=USD"
    ),
    "rabid_rabbit_markets.json": (
        "https://rabid-rabbit.org/api/public/v1/markets"
    ),
    "rabid_rabbit_orderbook.json": (
        "https://rabid-rabbit.org/api/public/v1/orderbook/RIN_USDT"
    ),
    "rabid_rabbit_trades.json": (
        "https://rabid-rabbit.org/api/public/v1/trades/RIN_USDT"
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--observation-id",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = (
        root
        / "evidence"
        / "exchange-observations"
        / args.observation_id
    )
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for filename, url in SOURCES.items():
        retrieved = utc_now()
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json,text/html,*/*;q=0.8",
                "User-Agent": "Rincoin-Exchange-Observation-Collector/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            status = int(response.status)
            content_type = response.headers.get("Content-Type", "")
        path = output / filename
        path.write_bytes(payload)
        rows.append(
            {
                "path": str(path.relative_to(root)),
                "source_url": url,
                "retrieved_utc": retrieved,
                "http_status": status,
                "content_type": content_type,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "observation_id": args.observation_id,
        "retrieved_utc": utc_now(),
        "files": rows,
        "notes": [
            "Run once per day; do not infer missing days.",
            "CoinPaprika aggregate and direct venue volume must not be added together.",
            "AtomicDEX/Gleec volume is represented only when a frozen source reports it.",
        ],
    }
    (output / "SOURCE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index = root / "evidence" / "exchange-observations.jsonl"
    with index.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "observation_id": args.observation_id,
                    "manifest": str(
                        (output / "SOURCE_MANIFEST.json").relative_to(root)
                    ),
                    "retrieved_utc": manifest["retrieved_utc"],
                },
                separators=(",", ":"),
            )
            + "\n"
        )
    print(output)


if __name__ == "__main__":
    main()
