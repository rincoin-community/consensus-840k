#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOGO_TARGET="includes/assets/rincoin.png"

copy_logo() {
  mkdir -p "$(dirname "$LOGO_TARGET")"

  if [[ -n "${RINCOIN_LOGO_SOURCE:-}" ]]; then
    if [[ ! -f "$RINCOIN_LOGO_SOURCE" ]]; then
      echo "RINCOIN_LOGO_SOURCE does not exist: $RINCOIN_LOGO_SOURCE" >&2
      exit 1
    fi
    cp "$RINCOIN_LOGO_SOURCE" "$LOGO_TARGET"
    return
  fi

  if [[ -f "$LOGO_TARGET" ]]; then
    return
  fi

  if [[ -f "/home/tomas_admin/rincoin/src/qt/res/icons/rincoin.png" ]]; then
    cp "/home/tomas_admin/rincoin/src/qt/res/icons/rincoin.png" "$LOGO_TARGET"
    return
  fi

  echo "Cannot find the Rincoin logo. Set RINCOIN_LOGO_SOURCE." >&2
  exit 1
}

copy_logo

python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(Path(".").rglob("*.json")):
    if ".cleanup-work" not in path.parts:
        json.loads(path.read_text(encoding="utf-8"))
for path in sorted(Path("scripts").glob("*.py")):
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
print("JSON parsing and in-memory Python compilation passed.")
PY

python3 scripts/simulate_monetary_scenarios.py
python3 scripts/verify_s6b_independently.py
python3 scripts/simulate_security_economics.py
python3 scripts/analyze_empirical_snapshot.py
python3 scripts/analyze_market_evidence.py

DOCUMENTS=(
  Rincoin_Monetary_Scenario_Analysis.qmd
  Rincoin_Monetary_Review_Summary.qmd
  Rincoin_Whitepaper_S1_Candidate.qmd
  Rincoin_Whitepaper_S5B_Candidate.qmd
  Rincoin_Whitepaper_S6B_Candidate.qmd
  Rincoin_840k_S1_Consensus_Change_Specification.qmd
  Rincoin_840k_S5B_Consensus_Change_Specification.qmd
  Rincoin_840k_S6B_Consensus_Change_Specification.qmd
)

for document in "${DOCUMENTS[@]}"; do
  quarto inspect "$document" >/dev/null
done

python3 scripts/validate_public_review.py
python3 scripts/validate_citations.py

if [[ "${SKIP_QUARTO_RENDER:-0}" != "1" ]]; then
  for document in "${DOCUMENTS[@]}"; do
    quarto render "$document"
  done
else
  for document in "${DOCUMENTS[@]}"; do
    pdf="${document%.qmd}.pdf"
    if [[ ! -f "$pdf" ]]; then
      echo "SKIP_QUARTO_RENDER=1 requires existing $pdf." >&2
      exit 1
    fi
  done
fi

python3 scripts/validate_public_review.py
python3 scripts/validate_citations.py --check-pdf

{
  printf "%s\n" \
    README.md \
    PUBLIC_REVIEW.md \
    LICENSES.md \
    CHANGE_SUMMARY.md \
    CITATION_AUDIT.md \
    PUBLICATION_CHECKLIST.md \
    REPOSITORY_CLEANUP_REPORT.md \
    SUMMARY_ANALYSIS_PARITY_AUDIT.md \
    UNRESOLVED_HUMAN_DECISIONS.md \
    LICENSE-SOFTWARE-MIT.txt \
    references.bib \
    chicago-author-date.csl \
    Rincoin_Monetary_Scenario_Analysis.qmd \
    Rincoin_Monetary_Scenario_Analysis.pdf \
    Rincoin_Monetary_Review_Summary.qmd \
    Rincoin_Monetary_Review_Summary.pdf \
    Rincoin_Whitepaper_S1_Candidate.qmd \
    Rincoin_Whitepaper_S1_Candidate.pdf \
    Rincoin_Whitepaper_S5B_Candidate.qmd \
    Rincoin_Whitepaper_S5B_Candidate.pdf \
    Rincoin_Whitepaper_S6B_Candidate.qmd \
    Rincoin_Whitepaper_S6B_Candidate.pdf \
    Rincoin_840k_S1_Consensus_Change_Specification.qmd \
    Rincoin_840k_S1_Consensus_Change_Specification.pdf \
    Rincoin_840k_S5B_Consensus_Change_Specification.qmd \
    Rincoin_840k_S5B_Consensus_Change_Specification.pdf \
    Rincoin_840k_S6B_Consensus_Change_Specification.qmd \
    Rincoin_840k_S6B_Consensus_Change_Specification.pdf
  find scripts data figures includes evidence -type f \
    ! -path '*/__pycache__/*' \
    ! -name '*.pyc' | sort
  find customized-halving original -type f | sort
} | sort -u | xargs sha256sum > MANIFEST.sha256

sha256sum -c MANIFEST.sha256
