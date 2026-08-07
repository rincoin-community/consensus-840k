#!/usr/bin/env python3
"""Validate the current Rincoin height-840,000 public-review package."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_QMDS = [
    ROOT / "Rincoin_Monetary_Scenario_Analysis.qmd",
    ROOT / "Rincoin_Monetary_Review_Summary.qmd",
    ROOT / "Rincoin_Whitepaper_S1_Candidate.qmd",
    ROOT / "Rincoin_Whitepaper_S5B_Candidate.qmd",
    ROOT / "Rincoin_Whitepaper_S6B_Candidate.qmd",
    ROOT / "Rincoin_840k_S1_Consensus_Change_Specification.qmd",
    ROOT / "Rincoin_840k_S5B_Consensus_Change_Specification.qmd",
    ROOT / "Rincoin_840k_S6B_Consensus_Change_Specification.qmd",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def front_matter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"Invalid YAML front matter: {path.name}")
    return text.split("\n---\n", 1)[0] + "\n"


def validate_public_metadata() -> None:
    for path in PUBLIC_QMDS:
        if not path.is_file():
            raise ValueError(f"Missing public QMD: {path.name}")
        metadata = front_matter(path)
        for exact in (
            'date: "2026-08-02"',
            'document-version: "1.0"',
            'status: "Discussion Draft"',
            'license: "CC-BY-4.0"',
        ):
            if exact not in metadata:
                raise ValueError(f"Missing {exact!r}: {path.name}")
        for obsolete in (
            "internal" + "-revision:",
            "intended-public-review" + "-date:",
            "CC-BY" + "-SA-4.0",
        ):
            if obsolete in metadata:
                raise ValueError(f"Obsolete metadata {obsolete!r}: {path.name}")
        text = path.read_text(encoding="utf-8")
        if text.count("<!--") != text.count("-->"):
            raise ValueError(f"Unbalanced comments: {path.name}")
        if text.count("```") % 2:
            raise ValueError(f"Unbalanced code fences: {path.name}")


def validate_json_and_csv() -> None:
    for path in sorted(ROOT.rglob("*.json")):
        if ".cleanup-work" in path.parts:
            continue
        json.loads(path.read_text(encoding="utf-8"))

    for path in sorted(ROOT.rglob("*.csv")):
        if ".cleanup-work" in path.parts:
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        if not rows or not rows[0] or any(not cell for cell in rows[0]):
            raise ValueError(f"Missing or invalid first-row CSV header: {path}")
        width = len(rows[0])
        for number, row in enumerate(rows[1:], 2):
            if len(row) != width:
                raise ValueError(
                    f"Inconsistent CSV field count: {path}:{number} "
                    f"({len(row)} != {width})"
                )
        if "vector_id" in rows[0]:
            index = rows[0].index("vector_id")
            ids = [row[index] for row in rows[1:]]
            if len(ids) != len(set(ids)) or any(not item for item in ids):
                raise ValueError(f"Duplicate or blank vector ID: {path}")


def read_csv(name: str) -> list[dict[str, str]]:
    with (ROOT / "data" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_scenarios_and_vectors() -> None:
    config = json.loads((ROOT / "data/scenario_config.json").read_text())
    metadata = config["metadata"]
    if metadata["document_version"] != "1.0":
        raise ValueError("Scenario configuration is not version 1.0")
    if metadata["publication_date"] != "2026-08-02":
        raise ValueError("Scenario configuration publication date changed")
    scenarios = {item["id"]: item for item in config["scenarios"]}
    expected_ids = {
        "S0", "S1", "S2a", "S2b", "S3", "S4", "S5a", "S5B",
        "S6a", "S6B", "S6c", "S7",
    }
    if set(scenarios) != expected_ids or ("S6" + "b") in scenarios:
        raise ValueError(f"Unexpected scenario identifiers: {sorted(scenarios)}")

    s6b = scenarios["S6B"]
    if s6b["kind"] != "bounded_height_phases_to_ceiling":
        raise ValueError("S6B is not the derived bounded height-only rule")
    if "end_height" in s6b["phases"][-1]:
        raise ValueError("S6B terminal height was entered instead of derived")
    preactivation = 210_000 * (
        5_000_000_000 + 2_500_000_000 + 1_250_000_000 + 625_000_000
    )
    issued_at_final_start = (
        preactivation
        + (2_100_000 - 840_000) * 400_000_000
        + (4_200_000 - 2_100_000) * 200_000_000
        + (6_300_000 - 4_200_000) * 100_000_000
    )
    ceiling = 168_000_000 * 100_000_000
    remaining = ceiling - issued_at_final_start
    if remaining % 60_000_000:
        raise ValueError("S6B final phase does not divide the ceiling exactly")
    first_zero = 6_300_000 + remaining // 60_000_000
    if first_zero != 234_587_500:
        raise ValueError(f"S6B first zero height changed: {first_zero}")

    summary = {row["scenario_id"]: row for row in read_csv("scenario_summary.csv")}
    expected_summary = {
        "S1": ("593750000", "73710000", "4462499301750000"),
        "S5B": ("625000000", "63630000", "4462499976900000"),
        "S6B": ("400000000", "234587500", "16800000000000000"),
    }
    for scenario_id, values in expected_summary.items():
        observed = (
            summary[scenario_id]["first_activation_subsidy_base_units"],
            summary[scenario_id]["first_zero_subsidy_height"],
            summary[scenario_id]["maximum_scheduled_issuance_base_units"],
        )
        if observed != values:
            raise ValueError(f"{scenario_id} summary changed: {observed}")

    vector_specs = {
        "S1_normative_test_vectors.csv": (
            "height", "maximum_permitted_subsidy_base_units",
            {839_999: 625_000_000, 840_000: 593_750_000, 73_710_000: 0},
        ),
        "S5B_normative_test_vectors.csv": (
            "height", "maximum_permitted_subsidy_base_units",
            {839_999: 625_000_000, 840_000: 625_000_000, 63_630_000: 0},
        ),
        "S6B_normative_test_vectors.csv": (
            "height", "maximum_subsidy_base_units",
            {
                839_999: 625_000_000,
                840_000: 400_000_000,
                2_100_000: 200_000_000,
                4_200_000: 100_000_000,
                6_300_000: 60_000_000,
                234_587_499: 60_000_000,
                234_587_500: 0,
            },
        ),
    }
    for filename, (height_field, subsidy_field, expected) in vector_specs.items():
        vectors = {
            int(row[height_field]): int(row[subsidy_field])
            for row in read_csv(filename)
        }
        for height, subsidy in expected.items():
            if vectors.get(height) != subsidy:
                raise ValueError(f"{filename} mismatch at height {height}")

    s6_rows = read_csv("S6B_normative_test_vectors.csv")
    required_heights = {
        839_999, 840_000, 840_001, 2_099_999, 2_100_000, 2_100_001,
        4_199_999, 4_200_000, 4_200_001, 6_299_999, 6_300_000,
        6_300_001, 234_587_498, 234_587_499, 234_587_500, 234_587_501,
    }
    if {int(row["height"]) for row in s6_rows} != required_heights:
        raise ValueError("S6B normative vector boundary set changed")
    final = next(row for row in s6_rows if row["height"] == "234587500")
    if final["cumulative_maximum_scheduled_issuance_before_block_base_units"] != str(ceiling):
        raise ValueError("S6B vectors do not reach exactly 168M")
    for row in s6_rows:
        if row["exact_claim_valid"] != "true" or row["one_base_unit_over_maximum_invalid"] != "true":
            raise ValueError(f"S6B claim-validity flag changed: {row['vector_id']}")

    for stem in ("S1", "S5B", "S6B"):
        hash_path = ROOT / "data" / f"{stem}_normative_test_vectors.sha256"
        for line in hash_path.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split(maxsplit=1)
            if sha256(ROOT / relative.strip()) != digest:
                raise ValueError(f"Vector hash mismatch: {relative}")

    independent = json.loads(
        (ROOT / "data/S6B_independent_verification.json").read_text()
    )
    if independent["status"] != "passed" or independent["first_zero_subsidy_height"] != first_zero:
        raise ValueError("Independent S6B verification did not pass")
    if independent["maximum_scheduled_issuance_base_units"] != ceiling:
        raise ValueError("Independent S6B maximum issuance changed")
    if not independent["underclaim_does_not_change_later_schedule"]:
        raise ValueError("Independent S6B underclaim assertion failed")


def validate_documents() -> None:
    summary = (ROOT / "Rincoin_Monetary_Review_Summary.qmd").read_text()
    analysis = (ROOT / "Rincoin_Monetary_Scenario_Analysis.qmd").read_text()
    for text, name in ((summary, "Summary"), (analysis, "Analysis")):
        for phrase in (
            "S1, S5/b and S6/b",
            "S5/a",
            "S0",
            "234,587,500",
            "168,000,000 RIN",
            "governance contingency",
        ):
            if phrase not in text:
                raise ValueError(f"{name} missing parity phrase: {phrase}")

    order = [
        "# Scenario Definitions",
        "# Deterministic Simulation Results",
        "## Evaluation by Criteria",
        "## S1 and S5/b as an Equal-Total-Issuance Comparison",
        "## S6/b as the Bounded Customized Halving Representative",
        "# Security Economics Analysis",
        "# Conclusions, Objections, and Review Questions",
    ]
    positions = [analysis.index(item) for item in order]
    if positions != sorted(positions):
        raise ValueError("Analysis dependency order is incorrect")
    prefix = analysis[: analysis.index("## Evaluation by Criteria")]
    if "S1 and S5/b are selected" in prefix or "principal public-review set is **S1" in prefix:
        raise ValueError("Analysis preselects candidates before full scoring")
    required_analysis = (
        "does not retroactively increase the source proposal's score",
        "The separate S7 code snapshot remains unbounded",
        "transaction_size_by_structure_table.qmd",
        "transaction_size_relationships_table.qmd",
        "known to contain maintainer test transactions",
        "no causality is inferred",
    )
    analysis_normalized = " ".join(analysis.split())
    for phrase in required_analysis:
        if phrase not in analysis_normalized:
            raise ValueError(f"Analysis missing required content: {phrase}")
    obsolete_figure = "figures/transaction_value_vs_" + "size.png"
    if obsolete_figure in analysis:
        raise ValueError("Obsolete transaction-value scatter is still referenced")
    if (ROOT / obsolete_figure).exists():
        raise ValueError("Obsolete transaction-value scatter still exists")

    summary_lower = summary.lower()
    for british in ("acknowledgement", "labelled", "behaviour", "normalised", "modelled"):
        if re.search(rf"\b{british}\b", summary_lower):
            raise ValueError(f"Summary retains British spelling: {british}")
    if "making issuance mathematically perpetual" in summary:
        raise ValueError("Summary contradicts bounded S6/b issuance")

    package_text = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "PUBLIC_REVIEW.md", "PUBLICATION_CHECKLIST.md")
    )
    for phrase in (
        "Rincoin_Whitepaper_S6B_Candidate",
        "Rincoin_840k_S6B_Consensus_Change_Specification",
        "S6B_normative_test_vectors",
    ):
        if phrase not in package_text:
            raise ValueError(f"Public package omits {phrase}")


def validate_relative_paths() -> None:
    documents = [
        *PUBLIC_QMDS,
        *sorted(ROOT.glob("*.md")),
    ]
    for path in documents:
        text = path.read_text(encoding="utf-8")
        references = re.findall(r"\{\{<\s*include\s+([^ >]+)\s*>\}\}", text)
        references += re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
        for reference in references:
            target = reference.strip().split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if target.startswith("[") or "]" in target:
                continue
            target_path = ROOT / target
            if target_path.suffix.lower() == ".pdf" and target_path.with_suffix(".qmd").is_file():
                continue
            if not target_path.is_file():
                raise ValueError(f"Broken relative link in {path.name}: {reference}")


def validate_clean_names_and_paths() -> None:
    revision_pattern = "revision(?:" + "|".join(str(number) for number in range(12, 18)) + ")"
    historical_name = re.compile(
        revision_pattern + r"|(?:^|[_ ()-])NEW(?:[_ ()-]|$)|\([12]\)",
        re.IGNORECASE,
    )
    bad_paths = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if ".cleanup-work" not in path.parts
        and historical_name.search(path.name)
    ]
    if bad_paths:
        raise ValueError(f"Historical names remain: {bad_paths}")
    for obsolete in (
        ROOT / "_archive",
        ROOT / "evidence" / ("revision" + "12"),
        ROOT / "evidence" / ("revision" + "13"),
    ):
        if obsolete.exists():
            raise ValueError(f"Historical directory remains: {obsolete}")

    active_paths = [
        ROOT / "data/scenario_config.json",
        ROOT / "scripts/regenerate_documents.sh",
        *sorted((ROOT / "scripts").glob("*.py")),
        *PUBLIC_QMDS,
    ]
    for path in active_paths:
        text = path.read_text(encoding="utf-8")
        if re.search(revision_pattern, text, re.IGNORECASE):
            raise ValueError(f"Stale revision path/label in active file: {path}")
        old_repository = "/home/tomas_admin/" + "rincoin-whitepaper"
        if old_repository in text:
            raise ValueError(f"Old repository path in active file: {path}")


def main() -> None:
    validate_public_metadata()
    validate_json_and_csv()
    validate_scenarios_and_vectors()
    validate_documents()
    validate_relative_paths()
    validate_clean_names_and_paths()
    print("Current Rincoin public-review source and generated-data validation passed.")


if __name__ == "__main__":
    main()
