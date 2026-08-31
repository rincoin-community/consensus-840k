# S1 — Unit Test Results

Commit `a8617fc73` (see [`build-manifest.json`](build-manifest.json)). Reproduce with:

```
cd rincoin-core && git checkout consensus/s1-testing
./scripts/build.sh
./src/test/test_rincoin --report_level=short
```

## Result

```
Running 532 test cases...
Test module "Rincoin Core Test Suite" has passed with:
  531 test cases out of 532 passed
  1 test case out of 532 passed with warnings
  8998302 assertions out of 8998302 passed
  1 failed warning
```

The one warning is pre-existing and unrelated to this branch: `script_tests.cpp`
skips `script_assets_test` because the `DIR_UNIT_TEST_DATA` environment
variable isn't set in this environment. Not a failure, not new.

## New suites added for S1

| Suite | File | What it covers |
| --- | --- | --- |
| `fork_subsidy_tests` | `src/test/fork_subsidy_tests.cpp` | Frozen subsidy vectors (cross-checked against `analysis/data/S1_normative_test_vectors.csv`, see below), pre-fork behavior unchanged, strictly-decreasing-across-epochs, and a regression guard that `GetBlockSubsidy(INT_MAX, ...)` completes in under a second (guards a DoS-relevant unbounded-loop bug found and fixed during development). |
| `fork_commitment_tests` | `src/test/fork_commitment_tests.cpp` | Build/parse round-trip and every commitment malformation case in the vector catalog — see [`commitment-test-vectors.md`](commitment-test-vectors.md) for the full cross-reference. |
| `fork_sig_id_tests` | `src/test/fork_sig_id_tests.cpp` | `sig_fork_id` sighash mixing: byte-identical when inactive (regression guard against every existing `sighash_tests.cpp` vector), diverges correctly when active, end-to-end real ECDSA sign/verify bound to activation state. |
| `fork_wallet_sign_tests` | `src/test/fork_wallet_sign_tests.cpp` | Wallet-side signing actually uses the forkid-aware path; written specifically because two real defects were found here during development (see below) that would not have been caught by validation-side tests alone. |

## Independent subsidy re-derivation

`verification/scripts/independently_derive_s1_schedule.py` computes the full,
every-epoch schedule from the recursive rule as published (`technology/consensus-transition.md`),
without importing `src/validation.cpp` or the analysis package's own
simulator — a second, independent implementation of the same rule, mirroring
`analysis/scripts/verify_s6b_independently.py`'s existing role for S6/b.
Running it (`python3 verification/scripts/independently_derive_s1_schedule.py`)
cross-checks its output against every applicable row of
`analysis/data/S1_normative_test_vectors.csv` and confirms exact agreement
across all 34 rows. Also used to generate the dense per-epoch series behind
[the subsidy-curve figure](../S1_Consensus_Testing_Summary.qmd) — the sparse
boundary-vector CSV is the right file to spot-check specific heights against
but is not dense enough to plot directly (see that script's own header
comment for why).

## Pre-existing suites re-run unmodified

Every other suite in the 532 (script, sighash, transaction, mempool, wallet,
PSBT, RPC, net, MWEB, etc.) ran unmodified and passed — i.e. this branch's
changes don't alter behavior for any caller that doesn't opt into the new
sighash/commitment logic.

## Two defects found by writing and running these tests, not by review

1. **Wallet-crash-on-unsynced-state.** `CWallet::SignTransaction()` and
   `FillPSBT()` originally called an internal accessor that `assert()`s if the
   wallet hasn't processed a block yet. That's a real, reachable state (e.g. a
   freshly loaded wallet), and the assertion aborted the whole process, not
   just the one call — first surfaced as 91 unrelated-looking test failures in
   a completely different subsystem, traced via debugger to this root cause.
   Fixed by reading the underlying state directly with a safe fallback instead
   of asserting.
2. **Signature creator's self-check used the wrong context.** The component
   that produces `sig_fork_id`-aware signatures held a reference to its own
   sighash context that, due to C++ member-initialization order, wasn't
   actually wired to the checker used for the component's own internal
   self-verification step. The result: correctly created, forkid-active
   signatures failed their own self-check — a real defect on the PSBT-signing
   path (confirmed by tracing the actual call sites, not a test-only
   artifact), caught by `fork_wallet_sign_tests.cpp`'s
   `forkid_creator_changes_signature` test, which calls the signing primitive
   directly rather than through a wrapper that happened to route around the
   bug.
