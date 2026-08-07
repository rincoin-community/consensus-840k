#!/usr/bin/env python3
"""Freeze market, event, and supplemental chain evidence for public review.

This collector is intentionally separate from document generation. The
The offline analyzer consumes only frozen files and never performs live RPC or
HTTP requests while rendering the document.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_PREFIX = "market-and-chain-snapshot-"
DEFAULT_RPC_URL = "http://127.0.0.1:9556/"
HALVING_HEIGHTS = (210_000, 420_000, 630_000)
FIRST_HALVING_PRE_WINDOW_SECONDS = 30 * 86_400


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_bytes(
    snapshot_dir: Path,
    filename: str,
    payload: bytes,
    source_url: str,
    retrieved_utc: str,
    status: int,
    content_type: str,
    manifest_rows: list[dict[str, Any]],
) -> None:
    path = snapshot_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    manifest_rows.append(
        {
            "path": str(path),
            "source_url": source_url,
            "retrieved_utc": retrieved_utc,
            "http_status": status,
            "content_type": content_type,
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
    )


def fetch(
    snapshot_dir: Path,
    filename: str,
    url: str,
    manifest_rows: list[dict[str, Any]],
    *,
    expected_statuses: tuple[int, ...] = (200,),
    timeout: int = 60,
    allow_transport_error: bool = False,
) -> int:
    retrieved = utc_now()
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/html,application/pdf;q=0.9,*/*;q=0.8",
            "User-Agent": "Rincoin-Market-Evidence-Collector/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        status = int(error.code)
        payload = error.read()
        content_type = error.headers.get("Content-Type", "")
    except urllib.error.URLError as error:
        if not allow_transport_error:
            raise
        status = 0
        payload = (
            json.dumps(
                {
                    "source_url": url,
                    "retrieved_utc": retrieved,
                    "transport_error": str(error.reason),
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        content_type = "application/json"
        expected_statuses = (*expected_statuses, 0)
    if status not in expected_statuses:
        raise RuntimeError(f"Unexpected HTTP status {status} for {url}")
    save_bytes(
        snapshot_dir,
        filename,
        payload,
        url,
        retrieved,
        status,
        content_type,
        manifest_rows,
    )
    print(f"frozen {filename}: HTTP {status}, {len(payload)} bytes", flush=True)
    return status


class JsonRpc:
    def __init__(self, url: str, cookie_path: Path) -> None:
        cookie = cookie_path.read_text(encoding="utf-8").strip()
        token = base64.b64encode(cookie.encode("utf-8")).decode("ascii")
        self.url = url
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self.next_id = 1

    def batch(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        requests = []
        request_ids = []
        for method, params in calls:
            request_id = self.next_id
            self.next_id += 1
            request_ids.append(request_id)
            requests.append(
                {
                    "jsonrpc": "1.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
        payload = json.dumps(requests).encode("utf-8")
        request = urllib.request.Request(self.url, data=payload, headers=self.headers)
        with urllib.request.urlopen(request, timeout=180) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        indexed = {int(item["id"]): item for item in decoded}
        results: list[Any] = []
        for request_id in request_ids:
            item = indexed[request_id]
            if item.get("error"):
                raise RuntimeError(f"RPC error for request {request_id}: {item['error']}")
            results.append(item["result"])
        return results

    def call(self, method: str, *params: Any) -> Any:
        return self.batch([(method, list(params))])[0]


def save_rpc_json(
    snapshot_dir: Path,
    filename: str,
    payload: Any,
    rpc_url: str,
    methods: str,
    manifest_rows: list[dict[str, Any]],
) -> None:
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True).encode("utf-8")
        + b"\n"
    )
    save_bytes(
        snapshot_dir,
        filename,
        encoded,
        f"{rpc_url.rstrip('/')}/ ({methods})",
        utc_now(),
        200,
        "application/json",
        manifest_rows,
    )


def collect_node_state(
    rpc: JsonRpc,
    snapshot_dir: Path,
    rpc_url: str,
    manifest_rows: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    info = rpc.batch(
        [
            ("getblockchaininfo", []),
            ("getmininginfo", []),
            ("getnetworkinfo", []),
            ("getchaintips", []),
        ]
    )
    names = (
        "node_blockchain_info.json",
        "node_mining_info.json",
        "node_network_info.json",
        "node_chain_tips.json",
    )
    methods = ("getblockchaininfo", "getmininginfo", "getnetworkinfo", "getchaintips")
    for filename, method, payload in zip(names, methods, info):
        save_rpc_json(
            snapshot_dir,
            filename,
            payload,
            rpc_url,
            method,
            manifest_rows,
        )

    hashes = rpc.batch([("getblockhash", [height]) for height in HALVING_HEIGHTS])
    headers = rpc.batch([("getblockheader", [block_hash, True]) for block_hash in hashes])
    stats = rpc.batch([("getblockstats", [block_hash]) for block_hash in hashes])
    halvings: dict[int, dict[str, Any]] = {}
    for height, block_hash, header, block_stats in zip(
        HALVING_HEIGHTS, hashes, headers, stats
    ):
        halvings[height] = {
            "height": height,
            "hash": block_hash,
            "header": header,
            "stats": block_stats,
        }
    save_rpc_json(
        snapshot_dir,
        "node_halving_blocks.json",
        [halvings[height] for height in HALVING_HEIGHTS],
        rpc_url,
        "getblockhash,getblockheader,getblockstats",
        manifest_rows,
    )
    return halvings


def collect_first_halving_extension(
    rpc: JsonRpc,
    snapshot_dir: Path,
    rpc_url: str,
    manifest_rows: list[dict[str, Any]],
    halving: dict[str, Any],
    existing_start_height: int,
    batch_size: int,
) -> None:
    cutoff = int(halving["header"]["time"]) - FIRST_HALVING_PRE_WINDOW_SECONDS
    current = existing_start_height - 1
    records_descending: list[dict[str, Any]] = []
    reached_cutoff = False

    while current >= 0 and not reached_cutoff:
        low = max(0, current - batch_size + 1)
        heights = list(range(low, current + 1))
        hashes = rpc.batch([("getblockhash", [height]) for height in heights])
        headers = rpc.batch(
            [("getblockheader", [block_hash, True]) for block_hash in hashes]
        )
        stats = rpc.batch([("getblockstats", [block_hash]) for block_hash in hashes])
        for height, block_hash, header, block_stats in zip(
            heights, hashes, headers, stats
        ):
            records_descending.append(
                {
                    "height": height,
                    "hash": block_hash,
                    "time": int(header["time"]),
                    "mediantime": int(header["mediantime"]),
                    "difficulty": header["difficulty"],
                    "chainwork": header["chainwork"],
                    "subsidy_base_units": int(block_stats["subsidy"]),
                    "total_fees_base_units": int(block_stats["totalfee"]),
                    "transactions_including_coinbase": int(block_stats["txs"]),
                    "non_coinbase_transactions": int(block_stats["txs"]) - 1,
                    "average_fee_per_non_coinbase_tx_base_units": int(
                        block_stats["avgfee"]
                    ),
                    "median_fee_per_non_coinbase_tx_base_units": int(
                        block_stats["medianfee"]
                    ),
                    "minimum_fee_base_units": int(block_stats["minfee"]),
                    "maximum_fee_base_units": int(block_stats["maxfee"]),
                    "non_coinbase_total_size_bytes": int(block_stats["total_size"]),
                }
            )
        oldest_time = min(int(header["time"]) for header in headers)
        print(
            f"supplemental halving history: heights {low}-{current}, "
            f"oldest={oldest_time}, cutoff={cutoff}",
            flush=True,
        )
        if oldest_time <= cutoff:
            reached_cutoff = True
        current = low - 1

    if not reached_cutoff:
        raise RuntimeError("Failed to reach the first-halving 30-day cutoff")

    rows = sorted(
        (row for row in records_descending if int(row["time"]) >= cutoff),
        key=lambda row: int(row["height"]),
    )
    path = snapshot_dir / "node_first_halving_pre30d_extension.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    manifest_rows.append(
        {
            "path": str(path),
            "source_url": (
                f"{rpc_url.rstrip('/')}/ "
                "(getblockhash,getblockheader,getblockstats; "
                f"heights {rows[0]['height']}-{rows[-1]['height']})"
            ),
            "retrieved_utc": utc_now(),
            "http_status": 200,
            "content_type": "application/gzip+jsonl",
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    )


def public_sources() -> list[tuple[str, str, tuple[int, ...]]]:
    quote = urllib.parse.urlencode
    rin_history = "https://api.coinpaprika.com/v1/tickers/rin-rincoin/historical?"
    btc_history = "https://api.coinpaprika.com/v1/tickers/btc-bitcoin/historical?"
    return [
        (
            "coinpaprika_rin_history_daily.json",
            rin_history
            + quote(
                {
                    "start": "2025-07-28",
                    "end": "2026-07-27",
                    "interval": "1d",
                }
            ),
            (200,),
        ),
        (
            "coinpaprika_btc_history_daily.json",
            btc_history
            + quote(
                {
                    "start": "2025-07-28",
                    "end": "2026-07-27",
                    "interval": "1d",
                }
            ),
            (200,),
        ),
        (
            "coinpaprika_rin_history_limit_response.json",
            rin_history
            + quote(
                {
                    "start": "2025-01-01",
                    "end": "2026-07-27",
                    "interval": "1d",
                }
            ),
            (402,),
        ),
        (
            "coinpaprika_rin_markets.json",
            "https://api.coinpaprika.com/v1/coins/rin-rincoin/markets?quotes=USD",
            (200,),
        ),
        (
            "livecoinwatch_rin.html",
            "https://www.livecoinwatch.com/price/RinCoin-_RIN",
            (200, 403),
        ),
        (
            "nestex_rin_usdt_ticker.json",
            "https://trade.nestex.one/api/cg/tickers/RIN_USDT",
            (200,),
        ),
        (
            "nestex_rin_usdt_orderbook.json",
            "https://trade.nestex.one/api/cg/orderbook/RIN_USDT?depth=0",
            (200,),
        ),
        (
            "nestex_rin_liquidity.html",
            "https://trade.nestex.one/ajax/liq_stats.aspx?cur=RIN",
            (200,),
        ),
        (
            "nestex_liquidity_method.html",
            "https://trade.nestex.one/liquidity-is-awesome",
            (200,),
        ),
        (
            "nestex_public_api.pdf",
            "https://trade.nestex.one/docs/Public%20API%20Document.pdf",
            (200,),
        ),
        (
            "mrr_rinhash_rigs.json",
            "https://www.miningrigrentals.com/api/v2/rig"
            "?type=rinhash&currency=BTC&limit=100",
            (200,),
        ),
        (
            "mrr_rinhash_market.html",
            "https://www.miningrigrentals.com/rigs/rinhash",
            (200,),
        ),
        (
            "rabid_rabbit_markets.json",
            "https://rabid-rabbit.org/api/public/v1/markets",
            (200,),
        ),
        (
            "rabid_rabbit_rin_usdt_orderbook.json",
            "https://rabid-rabbit.org/api/public/v1/orderbook/RIN_USDT",
            (200,),
        ),
        (
            "rabid_rabbit_rin_usdt_trades.json",
            "https://rabid-rabbit.org/api/public/v1/trades/RIN_USDT",
            (200,),
        ),
        (
            "explorer_summary.json",
            "https://explorer.rincoin.tech/ext/getsummary",
            (200,),
        ),
        (
            "explorer_basic_stats.json",
            "https://explorer.rincoin.tech/ext/getbasicstats",
            (200,),
        ),
        (
            "explorer_current_price.json",
            "https://explorer.rincoin.tech/ext/getcurrentprice",
            (200,),
        ),
        (
            "explorer_network_chart.json",
            "https://explorer.rincoin.tech/ext/getnetworkchartdata",
            (200,),
        ),
        (
            "explorer_last_orphans.json",
            "https://explorer.rincoin.tech/ext/getlastorphans/0/0/100",
            (200,),
        ),
        (
            "exbitron_home.html",
            "https://www.exbitron.com/",
            (200, 403),
        ),
        (
            "rincoin_community_forge_home.html",
            "https://rincoin.tech/",
            (200,),
        ),
        (
            "github_takologi_rincoin_repo.json",
            "https://api.github.com/repos/takologi/rincoin",
            (200,),
        ),
        (
            "github_takologi_rincoin_community_commit.json",
            "https://api.github.com/repos/takologi/rincoin/commits/"
            "0f2d7d8b6e8feec1f7986d25eb9bccbc3f4088d1",
            (200,),
        ),
        (
            "github_aevust_rincoin_rips_repo.json",
            "https://api.github.com/repos/Aevust/rincoin-rips",
            (200,),
        ),
        (
            "github_aevust_rincoin_rips_first_commit.json",
            "https://api.github.com/repos/Aevust/rincoin-rips/commits/"
            "596bfa9f0d91b2dda3517540d320231c78798d8a",
            (200,),
        ),
        (
            "github_aevust_rincoin_rips_initial_set_commit.json",
            "https://api.github.com/repos/Aevust/rincoin-rips/commits/"
            "ac3d4933a901404cc121ff10ee35be27644ce77c",
            (200,),
        ),
        (
            "github_aevust_rincoin_rips_authority_commit.json",
            "https://api.github.com/repos/Aevust/rincoin-rips/commits/"
            "aca430a4df8fdc096d348f7084ea63fd613ff23f",
            (200,),
        ),
        (
            "github_aevust_rincoin_rips_forks_commit.json",
            "https://api.github.com/repos/Aevust/rincoin-rips/commits/"
            "2a4b29fb8c27af0e4aa8f1ff8df16ce140fea6b0",
            (200,),
        ),
        (
            "github_aevust_rincoin_rips_sources_commit.json",
            "https://api.github.com/repos/Aevust/rincoin-rips/commits/"
            "4c9fbbbdb0968880ff3ee94b7815b2e188cba7e0",
            (200,),
        ),
    ]


OPTIONAL_TIMELINE_SOURCES = {
    "exbitron_home.html",
    "rincoin_community_forge_home.html",
    "github_takologi_rincoin_repo.json",
    "github_takologi_rincoin_community_commit.json",
    "github_aevust_rincoin_rips_repo.json",
    "github_aevust_rincoin_rips_first_commit.json",
    "github_aevust_rincoin_rips_initial_set_commit.json",
    "github_aevust_rincoin_rips_authority_commit.json",
    "github_aevust_rincoin_rips_forks_commit.json",
    "github_aevust_rincoin_rips_sources_commit.json",
}


def collect_tradebook_pages(
    snapshot_dir: Path,
    manifest_rows: list[dict[str, Any]],
    pages: int,
    delay_seconds: float,
) -> None:
    for page in range(1, pages + 1):
        filename = f"nestex_tradebook/page_{page:03d}.json"
        if (snapshot_dir / filename).exists():
            continue
        url = (
            "https://trade.nestex.one/api/cg/tradebook/"
            f"RIN_USDT?page={page}"
        )
        fetch(snapshot_dir, filename, url, manifest_rows)
        if page < pages:
            time.sleep(delay_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--snapshot-id",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
    )
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument(
        "--cookie",
        type=Path,
        default=Path("/home/tomas_admin/.cookie"),
    )
    parser.add_argument("--nestex-pages", type=int, default=60)
    parser.add_argument("--nestex-delay-seconds", type=float, default=6.1)
    parser.add_argument("--rpc-batch-size", type=int, default=250)
    parser.add_argument("--existing-history-start-height", type=int, default=177_801)
    args = parser.parse_args()

    root = args.root.resolve()
    stable_id = str(args.snapshot_id).replace("-", "").replace(":", "")
    snapshot_dir = root / "evidence" / f"{SNAPSHOT_PREFIX}{stable_id}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    manifest_rows: list[dict[str, Any]] = []

    for filename, url, statuses in public_sources():
        fetch(
            snapshot_dir,
            filename,
            url,
            manifest_rows,
            expected_statuses=statuses,
            allow_transport_error=filename in OPTIONAL_TIMELINE_SOURCES,
        )

    collect_tradebook_pages(
        snapshot_dir,
        manifest_rows,
        args.nestex_pages,
        args.nestex_delay_seconds,
    )

    rpc = JsonRpc(args.rpc_url, args.cookie)
    halvings = collect_node_state(
        rpc, snapshot_dir, args.rpc_url, manifest_rows
    )
    collect_first_halving_extension(
        rpc,
        snapshot_dir,
        args.rpc_url,
        manifest_rows,
        halvings[210_000],
        args.existing_history_start_height,
        args.rpc_batch_size,
    )

    manifest = {
        "collection_profile": "market-and-chain",
        "snapshot_id": args.snapshot_id,
        "collection_started_utc": started,
        "collection_finished_utc": utc_now(),
        "evidence_class": "frozen source responses",
        "notes": [
            "Rendering and analysis must not make live network calls.",
            "CoinPaprika historical rows are daily historical ticks, not guaranteed exchange closes.",
            "NestEx tradebook requests were rate-limited by the collector.",
            "Local-node source URLs identify RPC methods but never include credentials.",
        ],
        "files": sorted(manifest_rows, key=lambda row: row["path"]),
    }
    manifest_path = snapshot_dir / "SOURCE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(snapshot_dir)
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
