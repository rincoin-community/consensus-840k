#!/usr/bin/env python3
"""Freeze public and local-node evidence for the network-security snapshot.

This collector is intentionally separate from document regeneration. Rendering
uses only the frozen snapshot and never calls a live API.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_PREFIX = "network-and-security-snapshot-"
DEFAULT_RPC_URL = "http://127.0.0.1:9556/"


PUBLIC_SOURCES = {
    "explorer_summary.json": "https://explorer.rincoin.tech/ext/getsummary",
    "explorer_basic_stats.json": "https://explorer.rincoin.tech/ext/getbasicstats",
    "explorer_current_price.json": "https://explorer.rincoin.tech/ext/getcurrentprice",
    "explorer_network_chart.json": "https://explorer.rincoin.tech/ext/getnetworkchartdata",
    "explorer_orphan_index.txt": "https://explorer.rincoin.tech/ext/getorphanlist/0/1000",
    "mrr_rinhash_rigs.json": (
        "https://www.miningrigrentals.com/api/v2/rig"
        "?type=rinhash&currency=BTC&limit=100"
    ),
    "mrr_rinhash_market.html": "https://www.miningrigrentals.com/rigs/rinhash",
    "nestex_rin_usdt_ticker.json": "https://trade.nestex.one/api/cg/tickers/RIN_USDT",
    "nestex_rin_usdt_orderbook.json": (
        "https://trade.nestex.one/api/cg/orderbook/RIN_USDT?depth=0"
    ),
    "nestex_rin_usdt_tradebook.json": (
        "https://trade.nestex.one/api/cg/tradebook/RIN_USDT?page=1"
    ),
    "rabid_rabbit_markets.json": "https://rabid-rabbit.org/api/public/v1/markets",
    "rabid_rabbit_rin_usdt_orderbook.json": (
        "https://rabid-rabbit.org/api/public/v1/orderbook/RIN_USDT"
    ),
    "rabid_rabbit_rin_usdt_trades.json": (
        "https://rabid-rabbit.org/api/public/v1/trades/RIN_USDT"
    ),
    "kraken_xbt_usd_ticker.json": (
        "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_public(url: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Rincoin-Community-Forge-empirical-audit/1.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type", "")


class Rpc:
    def __init__(self, url: str, cookie_path: Path):
        cookie = cookie_path.read_text(encoding="utf-8").strip()
        self.url = url
        self.authorization = "Basic " + base64.b64encode(cookie.encode()).decode()
        self.next_id = 1

    def batch(self, calls: list[tuple[str, list[Any]]], timeout: int = 300) -> list[Any]:
        requests = []
        ids = []
        for method, params in calls:
            request_id = self.next_id
            self.next_id += 1
            ids.append(request_id)
            requests.append(
                {"jsonrpc": "1.0", "id": request_id, "method": method, "params": params}
            )
        request = urllib.request.Request(
            self.url,
            data=json.dumps(requests).encode(),
            headers={
                "Authorization": self.authorization,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        by_id = {item["id"]: item for item in payload}
        results = []
        for request_id in ids:
            item = by_id[request_id]
            if item.get("error") is not None:
                raise RuntimeError(f"RPC error for request {request_id}: {item['error']}")
            results.append(item["result"])
        return results

    def call(self, method: str, *params: Any) -> Any:
        return self.batch([(method, list(params))])[0]


def collect_chain_history(
    rpc: Rpc,
    output: Path,
    tip_height: int,
    tip_time: int,
    days: int,
    batch_size: int,
) -> dict:
    cutoff_time = tip_time - days * 86400

    # Locate the cutoff by block time, then include a buffer for timestamp
    # variance. Records are filtered by their actual timestamp below.
    low, high = 1, tip_height
    while low < high:
        midpoint = (low + high) // 2
        block_hash = rpc.call("getblockhash", midpoint)
        block_time = int(rpc.call("getblockheader", block_hash, True)["time"])
        if block_time < cutoff_time:
            low = midpoint + 1
        else:
            high = midpoint
    first_candidate = max(1, low - 500)
    stats_names = [
        "height",
        "blockhash",
        "time",
        "mediantime",
        "subsidy",
        "totalfee",
        "txs",
        "avgfee",
        "medianfee",
        "minfee",
        "maxfee",
        "total_size",
    ]
    retained = 0
    earliest_height = tip_height
    started = time.monotonic()
    with gzip.open(output, "wt", encoding="utf-8") as handle:
        for start in range(first_candidate, tip_height + 1, batch_size):
            end = min(tip_height + 1, start + batch_size)
            heights = list(range(start, end))
            stats = rpc.batch(
                [("getblockstats", [height, stats_names]) for height in heights]
            )
            headers = rpc.batch(
                [("getblockheader", [item["blockhash"], True]) for item in stats]
            )
            for stat, header in zip(stats, headers):
                if int(stat["time"]) < cutoff_time:
                    continue
                record = {
                    "height": int(stat["height"]),
                    "hash": stat["blockhash"],
                    "time": int(stat["time"]),
                    "mediantime": int(stat["mediantime"]),
                    "difficulty": header["difficulty"],
                    "chainwork": header["chainwork"],
                    "subsidy_base_units": int(stat["subsidy"]),
                    "total_fees_base_units": int(stat["totalfee"]),
                    "transactions_including_coinbase": int(stat["txs"]),
                    "non_coinbase_transactions": max(0, int(stat["txs"]) - 1),
                    "average_fee_per_non_coinbase_tx_base_units": int(stat["avgfee"]),
                    "median_fee_per_non_coinbase_tx_base_units": int(stat["medianfee"]),
                    "minimum_fee_base_units": int(stat["minfee"]),
                    "maximum_fee_base_units": int(stat["maxfee"]),
                    "non_coinbase_total_size_bytes": int(stat["total_size"]),
                }
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                retained += 1
                earliest_height = min(earliest_height, record["height"])
            if start == first_candidate or (start - first_candidate) % (batch_size * 25) == 0:
                elapsed = time.monotonic() - started
                print(
                    f"chain history: heights {start}-{end - 1}, "
                    f"retained {retained}, elapsed {elapsed:.1f}s",
                    flush=True,
                )
    return {
        "requested_days": days,
        "cutoff_unix": cutoff_time,
        "tip_height": tip_height,
        "earliest_retained_height": earliest_height,
        "retained_blocks": retained,
        "candidate_start_height": first_candidate,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--cookie", type=Path, default=Path("/home/tomas_admin/.cookie"))
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--history-days", type=int, default=365)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    root = Path.cwd()
    stable_id = args.snapshot_id.replace("-", "").replace(":", "")
    snapshot_dir = root / "evidence" / f"{SNAPSHOT_PREFIX}{stable_id}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "collection_profile": "network-and-security",
        "snapshot_id": args.snapshot_id,
        "collection_started_utc": utc_now(),
        "evidence_class": "frozen source responses",
        "files": [],
    }

    for filename, url in PUBLIC_SOURCES.items():
        retrieved = utc_now()
        status, body, content_type = fetch_public(url)
        path = snapshot_dir / filename
        path.write_bytes(body)
        manifest["files"].append(
            {
                "path": str(path.relative_to(root)),
                "source_url": url,
                "retrieved_utc": retrieved,
                "http_status": status,
                "content_type": content_type,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )
        print(f"public: {status} {url}", flush=True)

    rpc = Rpc(args.rpc_url, args.cookie)
    rpc_calls = {
        "node_blockchain_info.json": ("getblockchaininfo", []),
        "node_mining_info.json": ("getmininginfo", []),
        "node_chain_tips.json": ("getchaintips", []),
        "node_network_info.json": ("getnetworkinfo", []),
    }
    rpc_results = {}
    for filename, (method, params) in rpc_calls.items():
        retrieved = utc_now()
        result = rpc.call(method, *params)
        rpc_results[filename] = result
        path = snapshot_dir / filename
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["files"].append(
            {
                "path": str(path.relative_to(root)),
                "source_url": f"{args.rpc_url} JSON-RPC {method}",
                "retrieved_utc": retrieved,
                "http_status": 200,
                "content_type": "application/json",
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )

    blockchain = rpc_results["node_blockchain_info.json"]
    tip_height = int(blockchain["blocks"])
    tip_hash = blockchain["bestblockhash"]
    tip_header = rpc.call("getblockheader", tip_hash, True)
    tip_stats = rpc.call("getblockstats", tip_height)
    tip_path = snapshot_dir / "node_tip_block.json"
    tip_path.write_text(
        json.dumps({"header": tip_header, "stats": tip_stats}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    manifest["files"].append(
        {
            "path": str(tip_path.relative_to(root)),
            "source_url": f"{args.rpc_url} JSON-RPC getblockheader/getblockstats",
            "retrieved_utc": utc_now(),
            "http_status": 200,
            "content_type": "application/json",
            "sha256": sha256(tip_path),
            "bytes": tip_path.stat().st_size,
        }
    )

    history_path = snapshot_dir / "node_block_history_365d.jsonl.gz"
    history_meta = collect_chain_history(
        rpc,
        history_path,
        tip_height,
        int(tip_header["time"]),
        args.history_days,
        args.batch_size,
    )
    manifest["files"].append(
        {
            "path": str(history_path.relative_to(root)),
            "source_url": (
                f"{args.rpc_url} JSON-RPC getblockstats/getblockheader; "
                f"{args.history_days}-day window"
            ),
            "retrieved_utc": utc_now(),
            "http_status": 200,
            "content_type": "application/x-ndjson+gzip",
            "sha256": sha256(history_path),
            "bytes": history_path.stat().st_size,
            "collection": history_meta,
        }
    )

    manifest["collection_finished_utc"] = utc_now()
    manifest_path = snapshot_dir / "SOURCE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"snapshot: {snapshot_dir}")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
