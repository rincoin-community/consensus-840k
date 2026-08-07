# Rincoin Height-840,000 Consensus Review

This repository is the public discussion space for Rincoin's consensus decision at
block height 840,000. It contains review material, candidate documents, and
technical coordination documents; it does not adopt a candidate or announce that a
chain split is final. The first preference remains a common consensus and one chain.

**No scenario has been selected, preferred, or adopted.** Every candidate document
here is a discussion draft. The purpose of the package is to make the alternatives,
their assumptions, and their technical consequences available for public review.

## Start here

Two entry points, depending on how much detail you want:

- **[`Rincoin_Monetary_Review_Summary.pdf`](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Review_Summary.pdf)**
  — the short read: scenarios, findings, and open questions
  ([`.qmd` source](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Review_Summary.qmd),
  live HackMD discussion copy: https://hackmd.io/@takologi/SJ_6uVpSfx)
- **[`Rincoin_Monetary_Scenario_Analysis.pdf`](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Scenario_Analysis.pdf)**
  — the full **Rincoin Monetary Policy and Security Scenario Analysis**: twelve
  monetary schedules (S0–S7) compared over issuance, scarcity, activation shock,
  security economics, market depth, and attack cost, with the underlying data,
  evidence, and figures
  ([`.qmd` source](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Scenario_Analysis.qmd))

A HackMD discussion copy of the full analysis will follow; the summary already has
one (linked above).

## Candidate documents for three preselected scenarios

Three scenarios were preselected from the analysis for closer treatment. Each has a
**whitepaper draft** (how the Rincoin whitepaper would read under that schedule) and
a **consensus change specification draft** (the normative subsidy rule, activation
boundary, coinbase validation, and fixed test vectors). All six are watermarked
discussion drafts.

| Scenario | Schedule from height 840,000 | Whitepaper draft | Specification draft |
| --- | --- | --- | --- |
| **S1** — 1/20 reduction, no floor | Recursive 19/20 rule per epoch (nominally −5%) with integer-floor rounding, epoch length unchanged at 210,000 blocks (~5 months); no floor and no tail; permits at most ≈44,624,993 RIN | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S1_Candidate.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S1_Candidate.qmd) | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S1_Consensus_Change_Specification.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S1_Consensus_Change_Specification.qmd) |
| **S5/b** — extended epoch, phase-aligned to 630,000 | Epoch prolonged 10× to 2,100,000 blocks (~4 years) with the new epoch starting from height 630,000; subsidy stays 6.25 RIN through height 2,729,999, then binary halving; no floor and no tail; permits at most ≈44,624,999 RIN | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S5B_Candidate.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S5B_Candidate.qmd) | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S5B_Consensus_Change_Specification.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S5B_Consensus_Change_Specification.qmd) |
| **S6/b** — bounded Customized Halving, study scenario II | Customized Halving per Tokino's study: 4 RIN from 840,000, 2 RIN from 2,100,000, 1 RIN from 4,200,000, 0.6 RIN from 6,300,000, zero from 234,587,500; permits exactly 168,000,000 RIN | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S6B_Candidate.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S6B_Candidate.qmd) | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S6B_Consensus_Change_Specification.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S6B_Consensus_Change_Specification.qmd) |

All subsidy values are maximum permitted block subsidies in integer base units. The
schedules are height-only: they never use issued, circulating, spendable, lost, or
burned supply as a consensus input. Each specification covers the subsidy rule only —
chain separation, replay policy, release engineering, and activation coordination
are left to separate documents.

## Participate

Questions, criticism, corrections, and alternative interpretations are warmly
welcome. You can comment on HackMD, open a
[pull request](https://github.com/rincoin-community/consensus-840k/pulls),
[issue](https://github.com/rincoin-community/consensus-840k/issues), or
[Discussion](https://github.com/rincoin-community/consensus-840k/discussions), or
join the [Rincoin Community Forge](https://discord.gg/4PbKaFNgVw) Discord. See the
[coordination notice](coordination-notice.md) for current links and participation
instructions.

## Repository guide

- [`coordination-notice.md`](coordination-notice.md) invites direct technical
  coordination and lists the available response routes.
- [`STATUS.md`](STATUS.md) records the current publication and decision status.
- [`analysis/`](analysis/) contains the public review package:
  - `Rincoin_Monetary_Review_Summary.*` and `Rincoin_Monetary_Scenario_Analysis.*`
    — the summary and the full analysis, as `.qmd` source and rendered `.pdf`.
  - `Rincoin_Whitepaper_{S1,S5B,S6B}_Candidate.*` — the three whitepaper drafts.
  - `Rincoin_840k_{S1,S5B,S6B}_Consensus_Change_Specification.*` — the three
    consensus change specification drafts.
  - `*_full.qmd` — self-contained variants of the summary and the analysis with all
    includes expanded inline, for reading or pasting elsewhere as a single file.
  - [`data/`](analysis/data/) contains the machine-readable scenario configuration,
    simulation and comparison results, empirical series, and the normative test
    vectors generated for the candidate scenarios.
  - [`evidence/`](analysis/evidence/) contains frozen network, market, chain, and
    exchange snapshots together with provenance manifests, so the empirical claims
    can be re-checked against what was actually observed.
  - [`figures/`](analysis/figures/) contains the generated charts used by the
    documents.
  - [`includes/`](analysis/includes/) contains the generated tables and whitepaper
    text fragments that the `.qmd` sources pull in at render time.
  - [`scripts/`](analysis/scripts/) contains the Python and shell tooling that
    produced everything above: `collect_*.py` gather the raw evidence, `simulate_*.py`
    and `analyze_*.py` turn it into the data in `data/` plus the figures and includes,
    `verify_s6b_independently.py` re-derives S6/b from scratch as a cross-check,
    `validate_*.py` check citations and review readiness, and
    `regenerate_documents.sh` runs the whole pipeline and re-renders every document.
  - [`original/`](analysis/original/) contains the original Rincoin whitepaper.
  - [`customized-halving/`](analysis/customized-halving/) contains a preserved copy
    of Tokino's Customized Halving study and its validation/provenance document,
    used as source material in the review.
  - `references.bib` and `chicago-author-date.csl` are the shared bibliography and
    citation style.

## Reproducing the documents

The `.pdf` files are generated from the `.qmd` sources with
[Quarto](https://quarto.org/); the tables, figures, and data files they include are
generated by the scripts and are marked as such — they are not edited by hand.
[`scripts/regenerate_documents.sh`](analysis/scripts/regenerate_documents.sh) is the
pipeline that produced the package: it re-runs the simulations and analyses, rebuilds
the data files, figures, and includes, validates citations and review readiness, and
re-renders all eight documents with Quarto (`SKIP_QUARTO_RENDER=1` runs the data and
validation stages against the already-rendered PDFs). Its final packaging step also
checksums release files that are not part of this repository, so run the individual
scripts if you only want to reproduce a specific result.

Additional technical overview material, implementation code, and further
specifications will be added as their review and publication gates are reached.
