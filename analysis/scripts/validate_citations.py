#!/usr/bin/env python3
"""Validate shared bibliography use across the public-review document set."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent.parent
BIBLIOGRAPHY = ROOT / "references.bib"
CSL = ROOT / "chicago-author-date.csl"
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
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+([^ >]+)\s*>\}\}")
CITATION_RE = re.compile(r"(?<![\w./-])@([A-Za-z][A-Za-z0-9:_-]*)")
BIB_KEY_RE = re.compile(r"(?m)^@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,")


def expanded_source(path: Path, seen: set[Path] | None = None) -> str:
    seen = set() if seen is None else seen
    resolved = path.resolve()
    if resolved in seen:
        raise ValueError(f"Recursive include detected: {path}")
    seen.add(resolved)

    text = path.read_text(encoding="utf-8")
    chunks = [text]
    for reference in INCLUDE_RE.findall(text):
        include_path = (ROOT / reference).resolve()
        if not include_path.is_file():
            raise ValueError(f"Missing include referenced by {path.name}: {reference}")
        chunks.append(expanded_source(include_path, seen.copy()))
    return "\n".join(chunks)


def front_matter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Missing YAML front matter: {path.name}")
    try:
        return text.split("\n---\n", 1)[0] + "\n"
    except IndexError as exc:
        raise ValueError(f"Unterminated YAML front matter: {path.name}") from exc


def bibliography_keys() -> set[str]:
    if not BIBLIOGRAPHY.is_file():
        raise ValueError("Missing references.bib")
    keys = BIB_KEY_RE.findall(BIBLIOGRAPHY.read_text(encoding="utf-8"))
    if not keys:
        raise ValueError("No bibliography entries found")
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"Duplicate bibliography keys: {duplicates}")
    return set(keys)


def validate_sources() -> None:
    if not CSL.is_file():
        raise ValueError("Missing chicago-author-date.csl")

    known = bibliography_keys()
    used: set[str] = set()

    for path in PUBLIC_QMDS:
        metadata = front_matter(path)
        for required in (
            "bibliography: references.bib",
            "csl: chicago-author-date.csl",
            "link-citations: true",
        ):
            if required not in metadata:
                raise ValueError(f"Missing citation metadata in {path.name}: {required}")

        source = expanded_source(path)
        document_keys = set(CITATION_RE.findall(source))
        unresolved = sorted(document_keys - known)
        if unresolved:
            raise ValueError(f"Unresolved citation keys in {path.name}: {unresolved}")
        if "# References" not in source:
            raise ValueError(f"Missing References section in {path.name}")
        used.update(document_keys)

    orphaned = sorted(known - used)
    if orphaned:
        raise ValueError(f"Bibliography entries not cited by the package: {orphaned}")


def validate_pdfs() -> None:
    for source in PUBLIC_QMDS:
        pdf = source.with_suffix(".pdf")
        if not pdf.is_file():
            raise ValueError(f"Missing rendered PDF: {pdf.name}")
        reader = PdfReader(str(pdf))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        compact = " ".join(text.split())
        if "[?]" in text or "???" in text:
            raise ValueError(f"Missing-reference marker in {pdf.name}")
        leaked_keys = sorted(set(CITATION_RE.findall(text)))
        if leaked_keys:
            raise ValueError(f"Unrendered citation keys in {pdf.name}: {leaked_keys}")
        references_at = compact.rfind("References")
        if references_at < int(len(compact) * 0.55):
            raise ValueError(f"References are missing or misplaced in {pdf.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-pdf",
        action="store_true",
        help="also inspect rendered PDFs for unresolved citations and placement",
    )
    args = parser.parse_args()

    validate_sources()
    if args.check_pdf:
        validate_pdfs()
    print("Citation validation passed.")


if __name__ == "__main__":
    main()
