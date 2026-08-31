# S5/b — Unit Test Results

Commit `3cad3c7f2` (see [`build-manifest.json`](build-manifest.json)). Reproduce with:

```
cd rincoin-core && git checkout consensus/s5b-testing
./scripts/build.sh
./src/test/test_rincoin --report_level=short
```

## Result

```
Running 532 test cases...
Test module "Rincoin Core Test Suite" has passed with:
  531 test cases out of 532 passed
  1 test case out of 532 passed with warnings
  8833851 assertions out of 8833851 passed
  1 failed warning
```

The one warning is pre-existing and unrelated to this branch: `script_tests.cpp`
skips `script_assets_test` because the `DIR_UNIT_TEST_DATA` environment
variable isn't set in this environment. Not a failure, not new.

## Suite specific to this scenario

| Suite | File | What it covers |
| --- | --- | --- |
| `fork_subsidy_tests` | `src/test/fork_subsidy_tests.cpp` | Frozen S5/b subsidy vectors (cross-checked against `analysis/data/S5B_normative_test_vectors.csv`, see below), pre-fork behavior unchanged, flat-within-epoch-then-strictly-decreasing across phase boundaries, and a DoS-relevant regression guard that `GetBlockSubsidy(INT_MAX, ...)` completes in under a second. |

## Reused unmodified from `consensus/s1-testing`

`fork_commitment_tests`, `fork_sig_id_tests`, and `fork_wallet_sign_tests`
needed no changes for this scenario — they already read scenario identity
(`ForkBranchId`/`ForkScenarioId`/etc.) from `Consensus::Params` dynamically
rather than hardcoding S1's values, confirmed by direct code review before
branching. Every other pre-existing suite (script, sighash, transaction,
mempool, wallet, PSBT, RPC, net, MWEB, etc.) also ran unmodified and passed.

## Independent subsidy re-derivation

`verification/scripts/independently_derive_s5b_schedule.py` computes the
full, every-phase schedule from the formula as published
(`analysis/Rincoin_840k_S5B_Consensus_Change_Specification.qmd`), without
importing `src/validation.cpp` — a second, independent implementation of
the same publicly stated rule, mirroring
`independently_derive_s1_schedule.py`'s role for S1 and
`analysis/scripts/verify_s6b_independently.py`'s existing role for S6/b.
Running it (`python3 verification/scripts/independently_derive_s5b_schedule.py`)
cross-checks its output against every applicable row of
`analysis/data/S5B_normative_test_vectors.csv` and confirms exact agreement
across all 36 applicable rows (the 37th row is the pre-activation vector,
which uses the unchanged legacy rule and is correctly excluded). Also used
to generate the dense per-phase series behind the subsidy-curve figure in
the summary document — the sparse boundary-vector CSV is the right file to
spot-check specific heights against but is not dense enough to plot
directly.

## One real defect found while adapting the test suite, not by inspection

`feature_fork_subsidy.py`'s second epoch-boundary check assumed the next
subsidy change lands exactly one `nSubsidyHalvingInterval` past H1 — true
for S1 (whose post-fork epoch length equals `nSubsidyHalvingInterval`), but
S5/b's post-fork epoch is ten `nSubsidyHalvingInterval`s long, and H1 is
already one interval *into* that epoch (not at its start), so the real
next-change offset is nine intervals past H1, not one. On regtest that's
1,350 blocks — large enough to cross `FIRST_MWEB_HEIGHT` (432), past which
this test suite's hand-built blocks can't satisfy the MWEB extension-block/
HogEx requirement (unrelated machinery this scenario doesn't touch). Fixed
by adding a scenario-portable `FORK_SUBSIDY_NEXT_CHANGE_EPOCHS` constant and
falling back to a real-miner-based consistency check (inspecting the actual
node-mined coinbase, rather than hand-building an overclaim to reject) once
the target height is past MWEB activation. Full detail:
[`functional-test-results.md`](functional-test-results.md).
