#!/usr/bin/env python3
"""Freeze transaction value and serialized-size metrics for public review.

The script reuses the network snapshot's exact prevout-minus-output fee reconstruction
and fetches verbose transactions only to add serialization metrics. It does not
attempt to infer which output is a payment and which is change.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


DEFAULT_RPC_URL = "http://127.0.0.1:9556/"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class JsonRpc:
    def __init__(self, url: str, cookie_path: Path) -> None:
        token = base64.b64encode(
            cookie_path.read_text(encoding="utf-8").strip().encode("utf-8")
        ).decode("ascii")
        self.url = url
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self.next_id = 1

    def batch(self, calls: list[tuple[str, list[Any]]]) -> list[Any]:
        requests = []
        ids = []
        for method, params in calls:
            request_id = self.next_id
            self.next_id += 1
            ids.append(request_id)
            requests.append(
                {
                    "jsonrpc": "1.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
        request = urllib.request.Request(
            self.url,
            data=json.dumps(requests).encode("utf-8"),
            headers=self.headers,
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
        indexed = {int(item["id"]): item for item in payload}
        results = []
        for request_id in ids:
            item = indexed[request_id]
            if item.get("error"):
                raise RuntimeError(f"RPC error {request_id}: {item['error']}")
            results.append(item["result"])
        return results


def load_fee_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            txid = str(row["txid"])
            if txid in records:
                raise ValueError(f"Duplicate transaction in fee evidence: {txid}")
            records[txid] = row
    return records


def load_transaction_blocks(path: Path) -> list[dict[str, Any]]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            count = int(row["non_coinbase_transactions"])
            if count:
                rows.append(
                    {
                        "height": int(row["height"]),
                        "hash": str(row["hash"]),
                        "time": int(row["time"]),
                        "transaction_count": count,
                    }
                )
    return rows


def value_to_base_units(value: Decimal | str | float | int) -> int:
    return int((Decimal(str(value)) * Decimal(100_000_000)).to_integral_exact())


def append_manifest(
    manifest_path: Path,
    output_path: Path,
    metadata_path: Path,
    rpc_url: str,
    retrieved_utc: str,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing = {item["path"] for item in manifest["files"]}
    for path, content_type, source in (
        (
            output_path,
            "application/gzip+jsonl",
            f"{rpc_url.rstrip('/')}/ (getblock verbosity=2)",
        ),
        (
            metadata_path,
            "application/json",
            "derived collection metadata",
        ),
    ):
        relative = str(path)
        if relative in existing:
            raise ValueError(f"Manifest already contains {relative}")
        manifest["files"].append(
            {
                "path": relative,
                "source_url": source,
                "retrieved_utc": retrieved_utc,
                "http_status": 200,
                "content_type": content_type,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    manifest["files"] = sorted(manifest["files"], key=lambda row: row["path"])
    manifest["collection_finished_utc"] = utc_now()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-snapshot",
        default="evidence/network-and-security-snapshot-20260727T121555Z",
    )
    parser.add_argument(
        "--target-snapshot",
        default="evidence/market-and-chain-snapshot-20260727T163500Z",
    )
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument(
        "--cookie",
        type=Path,
        default=Path("/home/tomas_admin/.cookie"),
    )
    parser.add_argument("--block-batch-size", type=int, default=100)
    args = parser.parse_args()

    root = Path.cwd()
    source_dir = root / args.source_snapshot
    target_dir = root / args.target_snapshot
    manifest_path = target_dir / "SOURCE_MANIFEST.json"
    output_path = target_dir / "node_transaction_metrics_365d.jsonl.gz"
    metadata_path = target_dir / "node_transaction_metrics_metadata.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    if output_path.exists():
        raise FileExistsError(output_path)

    fee_records = load_fee_records(source_dir / "node_transaction_fees_365d.jsonl.gz")
    blocks = load_transaction_blocks(source_dir / "node_block_history_365d.jsonl.gz")
    rpc = JsonRpc(args.rpc_url, args.cookie)
    started = utc_now()
    records_written = 0
    total_fee = 0

    with gzip.open(output_path, "wt", encoding="utf-8", newline="\n") as output:
        for start in range(0, len(blocks), args.block_batch_size):
            expected_batch = blocks[start : start + args.block_batch_size]
            rpc_blocks = rpc.batch(
                [("getblock", [item["hash"], 2]) for item in expected_batch]
            )
            for expected, block in zip(expected_batch, rpc_blocks):
                if (
                    str(block["hash"]) != expected["hash"]
                    or int(block["height"]) != expected["height"]
                ):
                    raise ValueError(
                        f"Block identity mismatch at height {expected['height']}"
                    )
                transactions = block["tx"][1:]
                if len(transactions) != expected["transaction_count"]:
                    raise ValueError(
                        f"Transaction count mismatch at height {expected['height']}"
                    )
                for transaction in transactions:
                    txid = str(transaction["txid"])
                    fee_record = fee_records.pop(txid, None)
                    if fee_record is None:
                        raise ValueError(f"Missing exact-fee record for {txid}")
                    input_total = sum(
                        int(item["value_base_units"])
                        for item in fee_record["inputs"]
                    )
                    output_total = sum(
                        int(value) for value in fee_record["outputs_base_units"]
                    )
                    fee = int(fee_record["fee_base_units"])
                    if input_total - output_total != fee:
                        raise ValueError(f"Fee identity mismatch for {txid}")

                    output_values = [
                        value_to_base_units(item["value"])
                        for item in transaction["vout"]
                    ]
                    if output_values != [
                        int(value) for value in fee_record["outputs_base_units"]
                    ]:
                        raise ValueError(f"Output mismatch for {txid}")

                    hex_size = len(str(transaction["hex"])) // 2
                    size = int(transaction.get("size", hex_size))
                    if size != hex_size:
                        raise ValueError(f"Serialized-size mismatch for {txid}")
                    vsize = int(transaction.get("vsize", size))
                    weight = int(transaction.get("weight", vsize * 4))
                    row = {
                        "height": expected["height"],
                        "time": expected["time"],
                        "block_hash": expected["hash"],
                        "txid": txid,
                        "serialized_size_bytes": size,
                        "vsize_bytes": vsize,
                        "weight_units": weight,
                        "input_count": len(transaction["vin"]),
                        "output_count": len(transaction["vout"]),
                        "aggregate_input_value_base_units": input_total,
                        "aggregate_output_value_base_units": output_total,
                        "fee_base_units": fee,
                        "fee_rate_base_units_per_vbyte": (
                            str(Decimal(fee) / Decimal(vsize)) if vsize else None
                        ),
                        "payment_value_status": (
                            "not inferred; aggregate outputs include possible change"
                        ),
                    }
                    output.write(json.dumps(row, separators=(",", ":")) + "\n")
                    records_written += 1
                    total_fee += fee

            completed = min(start + args.block_batch_size, len(blocks))
            print(
                f"transaction metrics: {completed}/{len(blocks)} active blocks, "
                f"{records_written} transactions",
                flush=True,
            )

    if fee_records:
        raise ValueError(f"{len(fee_records)} fee records were not matched")

    finished = utc_now()
    metadata = {
        "collection_started_utc": started,
        "collection_finished_utc": finished,
        "source_fee_evidence": str(
            source_dir / "node_transaction_fees_365d.jsonl.gz"
        ),
        "source_fee_evidence_sha256": sha256(
            source_dir / "node_transaction_fees_365d.jsonl.gz"
        ),
        "source_block_history": str(
            source_dir / "node_block_history_365d.jsonl.gz"
        ),
        "source_block_history_sha256": sha256(
            source_dir / "node_block_history_365d.jsonl.gz"
        ),
        "transaction_records": records_written,
        "active_blocks": len(blocks),
        "total_reconstructed_fee_base_units": total_fee,
        "classification_note": (
            "Aggregate input and output values are observed transaction values. "
            "Payment value is not inferred because change outputs are unlabeled."
        ),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_manifest(
        manifest_path, output_path, metadata_path, args.rpc_url, finished
    )


if __name__ == "__main__":
    main()
