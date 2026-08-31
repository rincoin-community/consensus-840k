# S6/b — Unit Test Results

Commit `2cec8c6d9` (see [`build-manifest.json`](build-manifest.json)). Reproduce with:

```
cd rincoin-core && git checkout consensus/s6b-testing
./scripts/build.sh
./src/test/test_rincoin --report_level=short
```

## Result

```
Running 532 test cases...
Test module "Rincoin Core Test Suite" has passed with:
  531 test cases out of 532 passed
  1 test case out of 532 passed with warnings
  8968775 assertions out of 8968775 passed
  1 failed warning
```

The one warning is pre-existing and unrelated to this branch: `script_tests.cpp`
skips `script_assets_test` because the `DIR_UNIT_TEST_DATA` environment
variable isn't set in this environment. Not a failure, not new.

## Suite specific to this scenario

| Suite | File | What it covers |
| --- | --- | --- |
| `fork_subsidy_tests` | `src/test/fork_subsidy_tests.cpp` | Frozen S6/b subsidy vectors at every phase boundary and the derived terminal cutoff (cross-checked against `analysis/data/S6B_normative_test_vectors.csv`), pre-fork behavior unchanged, strictly-decreasing-then-terminates across the full `ForkSubsidyPhases` table, and a DoS-relevant regression guard that `GetBlockSubsidy(INT_MAX, ...)` completes in under a second. |

## A new `Consensus::Params` field, not just new test vectors

This scenario needed a genuine design decision beyond a formula swap: its
schedule is four fixed-value phases plus a cutoff *derived* from an
issuance ceiling, not a closed-form recursive/binary-halving rule. Before
implementing, `rincoin-core/rincoin@v1.1`'s own structurally similar
Customized Halving code was reviewed for lessons (at the user's explicit
request) — full account in the summary document's own section on this.
The result: `Consensus::Params::ForkSubsidyPhases`, a plain, ordered,
variable-length table of `{offset_from_h1, subsidy}` entries; `GetBlockSubsidy()`
`PostFork()` is a generic scan over it, not scenario-specific control flow.

## Reused unmodified from `consensus/s1-testing`

`fork_commitment_tests`, `fork_sig_id_tests`, and `fork_wallet_sign_tests`
needed no changes for this scenario — confirmed scenario-agnostic by direct
code review before branching. Every other pre-existing suite (script,
sighash, transaction, mempool, wallet, PSBT, RPC, net, MWEB, etc.) also ran
unmodified and passed.

## Independent verification

Unlike S1 and S5/b, S6/b's specification doesn't carry the same explicit
MUST/SHOULD independent-re-derivation language — but a real, pre-existing,
independent verification script already exists for it:
`analysis/scripts/verify_s6b_independently.py`, which does not import the
C++ implementation or the analysis package's own simulator. Running it
(`python3 analysis/scripts/verify_s6b_independently.py`) confirms the exact
terminal height (234,587,500) and issuance ceiling (168,000,000 RIN
exactly) this branch's `ForkSubsidyPhases` table encodes:

```
Independent S6/b verification passed: first zero height 234,587,500; exact maximum 168,000,000 RIN.
```

This script was reused directly, not duplicated — see the summary
document's Methods section for why writing a second one wasn't warranted.
