# Rincoin Height-840,000 Consensus Review

This repository is the public discussion and documentation space for Rincoin's consensus
transition at block height 840,000. It holds the monetary review, the candidate documents, the
technical specification that Rincoin Community Core 1.2.0 implements, and testing evidence. The
first preference remains a common consensus and one chain.

## Current status (2026-09-21)

- **Rincoin Community Forge has selected the S6/b scenario** (bounded, height-only customized
  halving: 4 / 2 / 1 / 0.6 RIN from heights 840,000 / 2,100,000 / 4,200,000 / 6,300,000, zero from
  234,587,500, 168,000,000 RIN maximum issuance) for its implementation, Rincoin Community Core
  1.2.0. S6/b was chosen because it offers the widest achievable compatibility with other Rincoin
  software and therefore the best chance of one chain. This is a decision about Community Core's
  own implementation, not a claim that the whole network has agreed.
- **Transactions** are kept apart from other continuations by the replay-protected signature hash
  of Bitcoin Cash and Bitcoin Gold (`SIGHASH_FORKID`, with the fork ID 840) from height 840,000;
  see [`technology/consensus-transition.md §5`](technology/consensus-transition.md#5-transaction-replay-protection-sighash_forkid).
  The required-transaction-version approach
  ("RIN3", RIP-0009) used by another implementation is not adopted, for the technical reasons in
  [`technology/response-to-rip-0009.md`](technology/response-to-rip-0009.md) (the August 2026
  assessment of RIP-0002 and RIP-0009) and in
  [`technology/replay-protection-comparison.md`](technology/replay-protection-comparison.md)
  (the comparison against the code as released).
- **Block 840,000** must claim exactly the maximum subsidy plus all fees, so that the unchanged
  rules reject it; see
  [`technology/consensus-transition.md §3`](technology/consensus-transition.md#3-the-coinbase-condition-in-block-840000).
- **No mandatory branch coinbase commitment** is introduced (the August design's `RINF` output is
  withdrawn); the compatibility consequences are stated exactly in
  [`technology/consensus-transition.md §4`](technology/consensus-transition.md#4-why-there-is-no-mandatory-branch-commitment).
- **Voluntary signalling** of Community Core templates uses the standard `getblocktemplate`
  field `coinbaseaux.flags`; it is not a consensus rule.
- **Coordination.** Community Forge will contact the maintainers of every known Rincoin
  implementation to align consensus and signature rules and keep one chain. No agreement exists
  at the time of writing.
- **Releases.** No 1.2.0 build has been published yet. A development build
  (`v1.2.0-dev.2`) has been built and tested by Community Forge; the executed tests, including a
  matrix of three implementations run against each other, are in
  [`verification/core-1.2.0-dev.2/`](verification/core-1.2.0-dev.2/). Its source will be published
  for testing after review; a stable production release is planned by **2026-09-30**, after
  verification. These are plans, not statements of production readiness. The previously published
  testing-mode branches (below) implement an older design and their results do not describe 1.2.0.

## Start here

Three different questions, three different starting points.

### Why is this happening, and how was the scenario chosen? (background)

- **[`Rincoin_Monetary_Review_Summary.pdf`](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Review_Summary.pdf)**
  — the short read: scenarios, findings, and open questions as of August 2026
  ([`.qmd` source](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Review_Summary.qmd),
  HackMD discussion copy: https://hackmd.io/@takologi/SJ_6uVpSfx)
- **[`Rincoin_Monetary_Scenario_Analysis.pdf`](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Scenario_Analysis.pdf)**
  — the full **Rincoin Monetary Policy and Security Scenario Analysis**: twelve monetary
  schedules (S0–S7) compared over issuance, scarcity, activation shock, security economics,
  market depth, and attack cost, with the underlying data, evidence, and figures
  ([`.qmd` source](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Monetary_Scenario_Analysis.qmd))

These documents are dated August 2026 and present S1, S5/b and S6/b as a public-review set. They
are kept as published; the selection of S6/b was made afterwards, on compatibility grounds, and
is recorded in this README and in [`STATUS.md`](STATUS.md).

### What actually changes, and what do I need to do? (technical specification)

For pool operators, exchanges, wallet or mining-software developers, and anyone who needs to know
what is mechanically changing.

- **[`technology/README.md`](technology/README.md)** — starts with a one-screen brief for
  integrators, then links the specification
  ([`consensus-transition.md`](technology/consensus-transition.md)), the replay-protection
  comparison, and the implementation and adoption plan.

### How do we know it works? (testing evidence)

- **[`verification/`](verification/)** — testing evidence. The evidence published so far
  (August–September 2026) covers the *testing-mode* implementations of the three candidates,
  including the now-withdrawn coinbase commitment; it is kept as historical evidence for those
  branches. Evidence for Rincoin Community Core 1.2.0 will be added when the build exists and the
  tests have actually been run.

## Candidate documents for the three preselected scenarios (August 2026)

Three scenarios were preselected from the analysis for closer treatment. Each has a
**whitepaper draft** and a **consensus change specification draft** (the normative subsidy rule,
activation boundary, coinbase validation, and fixed test vectors). S6/b was subsequently selected;
the S1 and S5/b documents remain available as the record of the review.

| Scenario | Schedule from height 840,000 | Whitepaper draft | Specification draft | Status |
| --- | --- | --- | --- | --- |
| **S1** — 1/20 reduction, no floor | Recursive 19/20 rule per epoch (nominally −5%) with integer-floor rounding, epoch length unchanged at 210,000 blocks (~5 months); no floor and no tail; permits at most ≈44,624,993 RIN | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S1_Candidate.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S1_Candidate.qmd) | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S1_Consensus_Change_Specification.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S1_Consensus_Change_Specification.qmd) | not selected; historical testing evidence in [`verification/S1_Consensus_Testing_Summary`](verification/S1_Consensus_Testing_Summary.qmd) |
| **S5/b** — extended epoch, phase-aligned to 630,000 | Epoch prolonged 10× to 2,100,000 blocks (~4 years) with the new epoch starting from height 630,000; subsidy stays 6.25 RIN through height 2,729,999, then binary halving; no floor and no tail; permits at most ≈44,624,999 RIN | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S5B_Candidate.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S5B_Candidate.qmd) | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S5B_Consensus_Change_Specification.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S5B_Consensus_Change_Specification.qmd) | not selected; historical testing evidence in [`verification/S5B_Consensus_Testing_Summary`](verification/S5B_Consensus_Testing_Summary.qmd) |
| **S6/b** — bounded Customized Halving, study scenario II | Customized Halving per Tokino's study: 4 RIN from 840,000, 2 RIN from 2,100,000, 1 RIN from 4,200,000, 0.6 RIN from 6,300,000, zero from 234,587,500; permits exactly 168,000,000 RIN | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S6B_Candidate.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_Whitepaper_S6B_Candidate.qmd) | [PDF](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S6B_Consensus_Change_Specification.pdf) · [QMD](https://github.com/rincoin-community/consensus-840k/blob/main/analysis/Rincoin_840k_S6B_Consensus_Change_Specification.qmd) | **selected (2026-09-19)**; historical testing-mode evidence in [`verification/S6B_Consensus_Testing_Summary`](verification/S6B_Consensus_Testing_Summary.qmd); 1.2.0 evidence to follow |

All subsidy values are maximum permitted block subsidies in integer base units. The schedules are
height-only: they never use issued, circulating, spendable, lost, or burned supply as a consensus
input. Each specification covers the subsidy rule only; the block-840,000 coinbase condition,
replay protection, release engineering, and activation coordination are covered in
[`technology/`](technology/). The S6/b specification's general statement that underclaiming is
always permitted is qualified with the block-840,000 exception (specification document version 1.1).

## Testing-mode implementations (August–September 2026, historical)

Each candidate had a testing-mode branch of `rincoin-community/rincoin-core`: an actual build of
the consensus code with the candidate's subsidy rule, the sighash-level fork identifier, and the
then-planned coinbase commitment, gated so it cannot run on mainnet by accident (it refuses to
start unless `RINCOIN_TESTING_ALLOW_MAINNET=1` is set in the process environment).

| Scenario | Branch | Commit tested |
| --- | --- | --- |
| S1 | [`consensus/s1-testing`](https://github.com/rincoin-community/rincoin-core/tree/consensus/s1-testing) | see `verification/S1/build-manifest.json` |
| S5/b | [`consensus/s5b-testing`](https://github.com/rincoin-community/rincoin-core/tree/consensus/s5b-testing) | see `verification/S5B/build-manifest.json` |
| S6/b | [`consensus/s6b-testing`](https://github.com/rincoin-community/rincoin-core/tree/consensus/s6b-testing) | `1e5a4201d` (2026-09-05), see `verification/S6B/build-manifest.json` |

Build and test (standard autotools build of `rincoin-core`, after checking a branch out):

```
./autogen.sh && ./configure && make -j"$(nproc)"   # build
./src/test/test_rincoin                            # unit tests
python3 test/functional/fork_report.py             # the six fork-scenario functional tests
```

What these branches represent, exactly: they are the record of the August–September testing of the
three candidates under the previous design. Their cross-implementation runs set each build against
two older Rincoin releases (`v1.1.0`, `v1.0.1`) and an independently developed foreign fork
(`Aevust/rincoin`, branch `feature/port-sim-v1.0.7`). Their published results (per branch: 532 unit tests,
6 fork-scenario functional tests, and the 159-test functional CI allowlist, all passing at the
commits recorded in `verification/`) are evidence for those branches at those commits. They are
**not** evidence for Rincoin Community Core 1.2.0, which drops the coinbase commitment, uses final
rather than synthetic identifier constants, adds the block-840,000 condition and the mempool
boundary handling, and will be published with its own evidence. Full details, exact commit hashes,
and reproduction commands for the historical runs are in each scenario's `verification/` annex.

## Participate

Questions, criticism, corrections, and alternative interpretations are welcome. You can comment on
HackMD, open a [pull request](https://github.com/rincoin-community/consensus-840k/pulls),
[issue](https://github.com/rincoin-community/consensus-840k/issues), or
[Discussion](https://github.com/rincoin-community/consensus-840k/discussions), or join the
[Rincoin Community Forge](https://discord.gg/4PbKaFNgVw) Discord. See the
[coordination notice](coordination-notice.md) for response routes (its August dates are
historical).

## Repository guide

- [`coordination-notice.md`](coordination-notice.md) is the August 2026 invitation to direct
  technical coordination; the response routes it lists are still valid.
- [`STATUS.md`](STATUS.md) records the current publication and decision status.
- [`technology/`](technology/) is the technical specification implemented by Rincoin Community
  Core 1.2.0: the S6/b rule, the block-840,000 coinbase condition, why no mandatory branch
  commitment is used and what that means for compatibility, the `SIGHASH_FORKID` replay protection
  with its exact constants, the voluntary signalling tag, the comparison with the
  required-transaction-version approach of another implementation, the adoption plan, and the
  August 2026 assessment of the external RIP-0002/RIP-0009 proposals
  (`response-to-rip-0009.md`). Starts with a brief for pool, exchange, wallet, and mining-software
  integrators.
- [`analysis/`](analysis/) contains the public review package (August 2026):
  - `Rincoin_Monetary_Review_Summary.*` and `Rincoin_Monetary_Scenario_Analysis.*`
    — the summary and the full analysis, as `.qmd` source and rendered `.pdf`.
  - `Rincoin_Whitepaper_{S1,S5B,S6B}_Candidate.*` — the three whitepaper drafts.
  - `Rincoin_840k_{S1,S5B,S6B}_Consensus_Change_Specification.*` — the three
    consensus change specification drafts; the S6/b one is the normative subsidy specification
    for 1.2.0.
  - `*_full.qmd` — self-contained variants of the summary and the analysis with all
    includes expanded inline.
  - [`data/`](analysis/data/) contains the machine-readable scenario configuration,
    simulation and comparison results, empirical series, and the normative test
    vectors generated for the candidate scenarios (`S6B_normative_test_vectors.*` are the
    frozen subsidy vectors for 1.2.0).
  - [`evidence/`](analysis/evidence/) contains frozen network, market, chain, and
    exchange snapshots together with provenance manifests.
  - [`figures/`](analysis/figures/) contains the generated charts used by the documents.
  - [`includes/`](analysis/includes/) contains the generated tables and whitepaper
    text fragments that the `.qmd` sources pull in at render time.
  - [`scripts/`](analysis/scripts/) contains the Python and shell tooling that
    produced everything above; `verify_s6b_independently.py` re-derives S6/b from scratch as a
    cross-check.
  - [`original/`](analysis/original/) contains the original Rincoin whitepaper.
  - [`customized-halving/`](analysis/customized-halving/) contains a preserved copy
    of Tokino's Customized Halving study and its validation/provenance document.
  - `references.bib` and `chicago-author-date.csl` are the shared bibliography and
    citation style.
- [`verification/`](verification/) contains per-scenario testing evidence: for each of the three
  candidates, a summary document (`S1_`, `S5B_`, `S6B_Consensus_Testing_Summary.*`) and an annex
  (`S1/`, `S5B/`, `S6B/`) with the acceptance matrix, test-vector catalog, unit- and
  functional-test results, exact binary/commit provenance, and the list of what was not covered.
  All of it describes the August–September testing-mode branches. Evidence for 1.2.0 will be added
  separately.

## Reproducing the documents

The `.pdf` files are generated from the `.qmd` sources with
[Quarto](https://quarto.org/); the tables, figures, and data files they include are
generated by the scripts and are marked as such.
[`scripts/regenerate_documents.sh`](analysis/scripts/regenerate_documents.sh) is the
pipeline that produced the package: it re-runs the simulations and analyses, rebuilds
the data files, figures, and includes, validates citations and review readiness, and
re-renders all documents with Quarto (`SKIP_QUARTO_RENDER=1` runs the data and
validation stages against the already-rendered PDFs). Its final packaging step also
checksums release files that are not part of this repository, so run the individual
scripts if you only want to reproduce a specific result.
