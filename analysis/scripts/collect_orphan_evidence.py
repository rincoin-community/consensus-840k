#!/usr/bin/env python3
"""Freeze paginated explorer orphan evidence for a network-security snapshot."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENDPOINT = "https://explorer.rincoin.tech/ext/getlastorphans/{minimum}/{start}/{length}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Rincoin-Community-Forge-empirical-audit/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status {response.status}: {url}")
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-dir",
        default="evidence/network-and-security-snapshot-20260727T121555Z",
    )
    parser.add_argument("--minimum-depth", type=int, default=0)
    parser.add_argument("--history-days", type=int, default=365)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    if args.page_size > 100:
        raise ValueError("Explorer limits orphan pages to 100 records")

    root = Path.cwd()
    snapshot_dir = root / args.snapshot_dir
    manifest_path = snapshot_dir / "SOURCE_MANIFEST.json"
    tip = json.loads((snapshot_dir / "node_tip_block.json").read_text(encoding="utf-8"))
    cutoff = int(tip["header"]["time"]) - args.history_days * 86400
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    page_entries: list[dict[str, Any]] = []
    start = 0

    while True:
        url = ENDPOINT.format(
            minimum=args.minimum_depth,
            start=start,
            length=args.page_size,
        )
        retrieved = utc_now()
        body = fetch(url)
        page = json.loads(body)
        if not isinstance(page, list):
            raise ValueError(f"Unexpected orphan endpoint response at offset {start}")
        page_path = snapshot_dir / f"explorer_last_orphans_{start:06d}.json"
        if page_path.exists():
            raise FileExistsError(page_path)
        page_path.write_bytes(body)
        entry = {
            "path": str(page_path.relative_to(root)),
            "source_url": url,
            "retrieved_utc": retrieved,
            "http_status": 200,
            "content_type": "application/json",
            "sha256": sha256(page_path),
            "bytes": page_path.stat().st_size,
        }
        page_entries.append(entry)
        records.extend(page)
        print(
            f"orphans: offset {start}, returned {len(page)}, "
            f"total {len(records)}",
            flush=True,
        )
        if not page:
            break
        timestamps = [int(item["timestamp"]) for item in page]
        if min(timestamps) < cutoff:
            break
        start += len(page)
        if len(page) < args.page_size:
            break

    timestamps = [int(item["timestamp"]) for item in records]
    if any(current > previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ValueError("Orphan endpoint is not in descending timestamp order")
    retained = [item for item in records if int(item["timestamp"]) >= cutoff]
    output_path = snapshot_dir / "explorer_last_orphans_365d.jsonl.gz"
    if output_path.exists():
        raise FileExistsError(output_path)
    with gzip.open(output_path, "wt", encoding="utf-8") as handle:
        for record in retained:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    manifest["files"].extend(page_entries)
    manifest["files"].append(
        {
            "path": str(output_path.relative_to(root)),
            "source_url": (
                "Derived frozen set from paginated "
                "https://explorer.rincoin.tech/ext/getlastorphans/0/start/100"
            ),
            "retrieved_utc": utc_now(),
            "http_status": 200,
            "content_type": "application/x-ndjson+gzip",
            "sha256": sha256(output_path),
            "bytes": output_path.stat().st_size,
            "collection": {
                "minimum_reorg_depth_parameter": args.minimum_depth,
                "semantics": (
                    "endpoint returns orphaned blocks with reorg_depth greater "
                    "than the minimum parameter"
                ),
                "history_days": args.history_days,
                "cutoff_unix": cutoff,
                "pages": len(page_entries),
                "records_retrieved": len(records),
                "records_retained": len(retained),
                "oldest_retrieved_unix": min(timestamps) if timestamps else None,
                "newest_retrieved_unix": max(timestamps) if timestamps else None,
                "coverage_reached_cutoff": (
                    bool(timestamps) and min(timestamps) < cutoff
                ),
            },
        }
    )
    manifest["orphan_collection_finished_utc"] = utc_now()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"orphan evidence: {output_path}")
    print(f"retained records: {len(retained)}")


if __name__ == "__main__":
    main()
