#!/usr/bin/env python3
"""Freeze exact transaction-fee evidence for a network-security snapshot.

The block-history collector stores authoritative per-block fee totals from
``getblockstats``. This companion collector reconstructs each non-coinbase
transaction fee from spent prevouts and transaction outputs, then requires the
sum to match the corresponding block total before writing the frozen dataset.
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


COIN = Decimal(100_000_000)
DEFAULT_RPC_URL = "http://127.0.0.1:9556/"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def value_to_base_units(value: Decimal | int | str) -> int:
    units = Decimal(value) * COIN
    integral = units.to_integral_exact()
    if units != integral:
        raise ValueError(f"Value has more than eight decimal places: {value}")
    return int(integral)


class DecimalRpc:
    def __init__(self, url: str, cookie_path: Path):
        cookie = cookie_path.read_text(encoding="utf-8").strip()
        self.url = url
        self.authorization = "Basic " + base64.b64encode(cookie.encode()).decode()
        self.next_id = 1

    def batch(self, calls: list[tuple[str, list[Any]]], timeout: int = 600) -> list[Any]:
        request_ids: list[int] = []
        payload: list[dict[str, Any]] = []
        for method, params in calls:
            request_id = self.next_id
            self.next_id += 1
            request_ids.append(request_id)
            payload.append(
                {"jsonrpc": "1.0", "id": request_id, "method": method, "params": params}
            )
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": self.authorization,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read(), parse_float=Decimal)
        by_id = {item["id"]: item for item in decoded}
        results: list[Any] = []
        for request_id in request_ids:
            item = by_id[request_id]
            if item.get("error") is not None:
                raise RuntimeError(f"RPC error for request {request_id}: {item['error']}")
            results.append(item["result"])
        return results


def transaction_outputs(tx: dict[str, Any]) -> list[int]:
    outputs: list[int] = []
    for index, item in enumerate(tx["vout"]):
        if int(item["n"]) != index:
            raise ValueError(f"Unexpected vout ordering in {tx['txid']}")
        outputs.append(value_to_base_units(item["value"]))
    return outputs


def fetch_missing_outputs(
    rpc: DecimalRpc,
    missing: set[str],
    cache: dict[str, list[int]],
    batch_size: int,
) -> None:
    ordered = sorted(missing)
    for start in range(0, len(ordered), batch_size):
        txids = ordered[start : start + batch_size]
        transactions = rpc.batch(
            [("getrawtransaction", [txid, True]) for txid in txids]
        )
        for txid, transaction in zip(txids, transactions):
            if transaction["txid"] != txid:
                raise ValueError(f"RPC returned wrong transaction for {txid}")
            cache[txid] = transaction_outputs(transaction)


def load_transaction_blocks(history_path: Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    with gzip.open(history_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if int(record["non_coinbase_transactions"]) > 0:
                blocks.append(
                    {
                        "height": int(record["height"]),
                        "hash": record["hash"],
                        "transaction_count": int(record["non_coinbase_transactions"]),
                        "total_fees_base_units": int(record["total_fees_base_units"]),
                    }
                )
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-dir",
        default="evidence/network-and-security-snapshot-20260727T121555Z",
    )
    parser.add_argument("--cookie", type=Path, default=Path("/home/tomas_admin/.cookie"))
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--block-batch-size", type=int, default=250)
    parser.add_argument("--transaction-batch-size", type=int, default=500)
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_dir = root / args.snapshot_dir
    manifest_path = snapshot_dir / "SOURCE_MANIFEST.json"
    history_path = snapshot_dir / "node_block_history_365d.jsonl.gz"
    output_path = snapshot_dir / "node_transaction_fees_365d.jsonl.gz"
    if output_path.exists():
        raise FileExistsError(output_path)

    blocks = load_transaction_blocks(history_path)
    rpc = DecimalRpc(args.rpc_url, args.cookie)
    outputs_cache: dict[str, list[int]] = {}
    transaction_count = 0
    reconstructed_fees = 0

    with gzip.open(output_path, "wt", encoding="utf-8") as output:
        for start in range(0, len(blocks), args.block_batch_size):
            batch_meta = blocks[start : start + args.block_batch_size]
            rpc_blocks = rpc.batch(
                [("getblock", [item["hash"], 2]) for item in batch_meta]
            )

            transactions_by_block: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
            missing_prevouts: set[str] = set()
            for expected, block in zip(batch_meta, rpc_blocks):
                if block["hash"] != expected["hash"] or int(block["height"]) != expected["height"]:
                    raise ValueError(f"Block identity mismatch at height {expected['height']}")
                transactions = block["tx"]
                if len(transactions) - 1 != expected["transaction_count"]:
                    raise ValueError(f"Transaction count mismatch at height {expected['height']}")
                for transaction in transactions:
                    outputs_cache[transaction["txid"]] = transaction_outputs(transaction)
                non_coinbase = transactions[1:]
                for transaction in non_coinbase:
                    for txin in transaction["vin"]:
                        prev_txid = txin.get("txid")
                        if prev_txid is None:
                            raise ValueError(
                                f"Cannot reconstruct non-standard input in {transaction['txid']}"
                            )
                        if prev_txid not in outputs_cache:
                            missing_prevouts.add(prev_txid)
                transactions_by_block.append((expected, non_coinbase))

            fetch_missing_outputs(
                rpc,
                missing_prevouts,
                outputs_cache,
                args.transaction_batch_size,
            )

            for expected, transactions in transactions_by_block:
                block_fee = 0
                for transaction in transactions:
                    input_records: list[dict[str, Any]] = []
                    input_total = 0
                    for txin in transaction["vin"]:
                        prev_txid = txin["txid"]
                        prev_index = int(txin["vout"])
                        try:
                            prev_value = outputs_cache[prev_txid][prev_index]
                        except (KeyError, IndexError) as error:
                            raise ValueError(
                                f"Missing prevout {prev_txid}:{prev_index}"
                            ) from error
                        input_total += prev_value
                        input_records.append(
                            {
                                "txid": prev_txid,
                                "vout": prev_index,
                                "value_base_units": prev_value,
                            }
                        )
                    output_values = transaction_outputs(transaction)
                    output_total = sum(output_values)
                    fee = input_total - output_total
                    if fee < 0:
                        raise ValueError(f"Negative fee for {transaction['txid']}: {fee}")
                    block_fee += fee
                    transaction_count += 1
                    reconstructed_fees += fee
                    output.write(
                        json.dumps(
                            {
                                "height": expected["height"],
                                "block_hash": expected["hash"],
                                "txid": transaction["txid"],
                                "inputs": input_records,
                                "outputs_base_units": output_values,
                                "fee_base_units": fee,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                if block_fee != expected["total_fees_base_units"]:
                    raise ValueError(
                        f"Fee mismatch at height {expected['height']}: "
                        f"reconstructed={block_fee}, getblockstats="
                        f"{expected['total_fees_base_units']}"
                    )

            if start == 0 or start % (args.block_batch_size * 20) == 0:
                print(
                    f"fee evidence: {min(start + len(batch_meta), len(blocks))}/"
                    f"{len(blocks)} transaction-bearing blocks, "
                    f"{transaction_count} transactions",
                    flush=True,
                )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fee_collection_finished = utc_now()
    manifest["files"].append(
        {
            "path": str(output_path.relative_to(root)),
            "source_url": (
                f"{args.rpc_url} JSON-RPC getblock/getrawtransaction; "
                "prevout-minus-output fee reconstruction"
            ),
            "retrieved_utc": fee_collection_finished,
            "http_status": 200,
            "content_type": "application/x-ndjson+gzip",
            "sha256": sha256(output_path),
            "bytes": output_path.stat().st_size,
            "collection": {
                "transaction_bearing_blocks": len(blocks),
                "non_coinbase_transactions": transaction_count,
                "reconstructed_total_fees_base_units": reconstructed_fees,
                "cross_check": (
                    "Every reconstructed block total equals getblockstats totalfee."
                ),
            },
        }
    )
    manifest["transaction_fee_collection_finished_utc"] = fee_collection_finished
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"fee evidence: {output_path}")
    print(f"transactions: {transaction_count}")
    print(f"total fees, base units: {reconstructed_fees}")


if __name__ == "__main__":
    main()
