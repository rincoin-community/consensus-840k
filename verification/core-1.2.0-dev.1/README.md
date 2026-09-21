# Rincoin Community Core 1.2.0 — evidence for the first development build (`v1.2.0-dev.1`)

Date: 2026-09-21 (production build, matrix and chain re-validation: 2026-09-20)

This directory records what was built and which tests were actually run for the first development
build of Rincoin Community Core 1.2.0, the release line that implements the height-840,000
transition specified in [`../../technology/consensus-transition.md`](../../technology/consensus-transition.md).

**What this is, and is not.** `v1.2.0-dev.1` is a label for a development build. It is not a tag, not
a release and not production software; it refuses to start on mainnet without an explicit
environment variable, and it never ran on, or connected to, the public Rincoin network. At the time
of writing its source has not been published; the commit IDs in
[`build-manifest.json`](build-manifest.json) identify it and become verifiable when it is. A
successful build and passing tests are evidence about this build, not a statement that a release is
ready.

Unlike the older annexes next to this one (`S1/`, `S5B/`, `S6B/`), which belong to the testing-mode
branches of August–September 2026 and their withdrawn coinbase commitment, everything here was
produced with the rules as finally specified: the S6/b schedule, the exact coinbase claim in the
transition block, the 16-byte `sig_fork_id`, the `SIGHASH_SINGLE` rule, the voluntary coinbase tag,
and no mandatory marker of any kind.

## Contents

| File | What it holds |
|---|---|
| [`build-manifest.json`](build-manifest.json) | source identity, the two build configurations, toolchains, dependency versions, SHA-256 of every binary |
| [`unit-test-results.md`](unit-test-results.md) | `make check`: commands, counts, the one skip, the 18 test cases added for the transition |
| [`functional-test-results.md`](functional-test-results.md) | the functional suite on both builds: counts, the one failed run and its cause, baseline failures, skips, the six new tests and what each establishes, a mutation check |
| [`cross-implementation.md`](cross-implementation.md) | three real implementations against each other on regtest: identities and hashes, what was aligned and how, the patch and its differential check, findings |
| [`cross-implementation-tables.md`](cross-implementation-tables.md) | the generated tables of all 190 recorded verdicts |
| [`cross-implementation-results.json`](cross-implementation-results.json), [`legacy-build-differential-check.json`](legacy-build-differential-check.json) | the raw results |
| [`patches/`](patches/) | the patches applied to the other implementations for testing |
| [`scripts/`](scripts/) | the harness, the differential check, the container wrapper, the table generator |
| [`open-items.md`](open-items.md) | what was not tested, known limitations, the test-suite baseline |

## Summary of results

| What | Result |
|---|---|
| Unit tests (`make check`, development configuration) | passed; 551 test cases, 1 of them a skip |
| Functional tests, CI allowlist (164), production configuration | 164 passed (after one earlier run with one failure caused by a race in a test; see the results file) |
| Functional tests, CI allowlist, development configuration | 164 passed |
| Functional tests, complete base set | 178 passed, 42 skipped, 2 baseline failures |
| Cross-implementation matrix | 190 verdicts, identical in four runs; every expectation of the specification about the other implementations confirmed |
| Offline re-validation of the whole mainnet block chain with full signature checking | all 747,987 blocks (tip `00000004d11d51ec…1ffe34`, 2026-09-20) accepted by the production-configuration binary with `-reindex-chainstate -assumevalid=0`, without any network connection, in 21 minutes; no consensus error; the resulting coin supply of 19,112,375 RIN equals the schedule |

## Reproducing

The tests are part of the `rincoin-core` source tree (`src/test/s6b_*_tests.cpp`,
`test/functional/feature_s6b_*.py`, `test/functional/wallet_s6b_signing.py`) and run with
`make check` and `test/functional/test_runner.py`. The cross-implementation harness needs the three
binaries named in [`cross-implementation.md`](cross-implementation.md):

```
python3 scripts/cal_matrix.py --framework <rincoin-core>/test/functional --workdir <empty dir> \
    --out results.json --c-bin <C rincoind> --a-bin <A rincoind or the container wrapper> \
    --l-bin <patched L rincoind> --cli <any rincoin-cli>
python3 scripts/render_matrix.py results.json tables.md
```
