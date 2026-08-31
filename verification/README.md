# Rincoin Consensus Transition — Verification

**No scenario has been selected, preferred, or adopted.** This directory does not
argue for S1, S5/b, or S6/b. It answers a narrower question, one scenario at a
time, once that scenario has a testing-mode implementation: *if this schedule
is the one eventually chosen, does the code that implements it actually hold up*
— against its own specification, against itself under reorgs and restarts, and
against other, differently-behaving node software it will meet in the wild?

`technology/` describes what changes and why. `analysis/` describes why a change
is being considered at all. This directory is the third leg: evidence that the
mechanism described in `technology/` was actually built and actually tested, not
just designed.

## Start here

- **[`S1_Consensus_Testing_Summary.pdf`](S1_Consensus_Testing_Summary.pdf)** —
  the short read: what was tested, how, and the headline results, in a few pages
  ([`.qmd` source](S1_Consensus_Testing_Summary.qmd)).
- **[`S1/`](S1/)** — the full evidence annex: the acceptance matrix, the
  commitment test-vector catalog as actually exercised, unit- and
  functional-test results, exact binary/commit provenance, and an honest list
  of what isn't covered yet.

Everything here concerns a **testing-mode build only** — a build that refuses to
run on mainnet unless an explicit environment variable is set at every
invocation (`RINCOIN_TESTING_ALLOW_MAINNET=1`). Nothing described in this
directory has run, or is capable of running, against the live Rincoin network.

## Scenarios covered

Testing evidence is published per scenario, once that scenario has a
testing-mode implementation to test. The mechanism under test (scheduled
coinbase commitment, `sig_fork_id`) is shared across all three candidates,
including the `branch_id` and `fork_no` values — only the subsidy schedule
and the (provisional, ad-hoc pending official assignment) `scenario_id`
differ per scenario, so each branch reuses the same evidence structure.

| Scenario | Testing-mode implementation | Testing evidence |
| --- | --- | --- |
| **S1** — 1/20 reduction, no floor | [`consensus/s1-testing`](https://github.com/rincoin-community/rincoin-core/tree/consensus/s1-testing), `rincoin-community/rincoin-core` | [`S1_Consensus_Testing_Summary.pdf`](S1_Consensus_Testing_Summary.pdf) · [annex](S1/) |
| **S5/b** — extended epoch, phase-aligned to 630,000 | [`consensus/s5b-testing`](https://github.com/rincoin-community/rincoin-core/tree/consensus/s5b-testing), branched from `consensus/s1-testing` | [`S5B_Consensus_Testing_Summary.pdf`](S5B_Consensus_Testing_Summary.pdf) · [annex](S5B/) |
| **S6/b** — bounded Customized Halving | [`consensus/s6b-testing`](https://github.com/rincoin-community/rincoin-core/tree/consensus/s6b-testing), branched from `consensus/s1-testing` | [`S6B_Consensus_Testing_Summary.pdf`](S6B_Consensus_Testing_Summary.pdf) · [annex](S6B/) |

All three branches are pushed; CI is enabled (`.github/workflows/ci.yml`'s
`fork-scenario-tests` job) and was still in progress on all three as of this
writing — see each scenario's own summary/annex for the exact run link and
current status.

## What "tested" means here

Four things, for whichever scenario has a row above:

1. **Unit-level correctness** — the subsidy schedule, the coinbase-commitment
   format, and the `sig_fork_id` sighash mixing, checked against frozen
   vectors (including, for S1, direct agreement with
   [`analysis/data/S1_normative_test_vectors.csv`](../analysis/data/S1_normative_test_vectors.csv),
   the vector set the specification itself names as the conformance target).
2. **Single-node functional correctness** — commitment validation, subsidy
   enforcement, and transaction replay protection, exercised end-to-end
   against a running node via RPC and P2P, not just in-process.
3. **Multi-node correctness** — two testing-mode nodes reorganizing across the
   activation boundary, confirming higher work wins only when the chain is
   also rule-valid.
4. **Cross-implementation correctness** — the testing-mode build set against
   older Rincoin releases and against other, independently-developed Rincoin
   forks it may encounter on a shared network, each tested as both block
   *producer* and block *validator* against the others, with expected outcomes
   taken from the frozen vectors above, never from any implementation's own
   output.

What this directory does **not** claim: readiness for mainnet deployment, a
release-engineering rollout plan, or resolution of ecosystem-wide replay/wallet/
exchange concerns — those are separate, later gates (see `technology/`'s "What
we won't do" for now, and the open items list in each scenario's annex for what
this testing deliberately left out).

## Reproducing this evidence

Same pattern as `analysis/`: `.qmd` sources render to PDF with
[Quarto](https://quarto.org/); tables and figures under `includes/`, `data/`,
and `figures/` are generated, not hand-edited, and are pulled in at render
time. [`scripts/regenerate_verification.sh`](scripts/regenerate_verification.sh)
rebuilds this directory's own artifacts from the underlying test results. The
tests themselves — unit, functional, and cross-implementation — run against the
`rincoin-core` source tree; see each scenario's annex for the exact commit,
build flags, and commands used.
