# Rincoin Community Core 1.2.0 — evidence for the development build `v1.2.0-dev.2`

Date: 2026-09-26 (first version 2026-09-21)

This directory records what was built and which tests were actually run for the current development
build of Rincoin Community Core 1.2.0, the release line that implements the height-840,000
transition specified in [`../../technology/consensus-transition.md`](../../technology/consensus-transition.md) and
leaves MWEB unactivated on mainnet.

**What this is, and is not.** `v1.2.0-dev.2` is a label for a development build. It is not a tag, not
a release and not production software; it refuses to start on mainnet without an explicit
environment variable, and it never ran on, or connected to, the public Rincoin network. Its source is
published as branch `consensus/840k-s6b` of `rincoin-community/rincoin-core`; the commit IDs in
[`build-manifest.json`](build-manifest.json) identify it. The binaries tested here are the release
build made by the project's GitHub Actions workflow, and a second build of the same commit on
another machine produced bit-identical node, command-line, transaction and wallet binaries. A
successful build and passing tests are evidence about this build, not a statement that a release is
ready.

Unlike the older annexes next to this one (`S1/`, `S5B/`, `S6B/`), which belong to the testing-mode
branches of August–September 2026 and their withdrawn coinbase commitment, everything here was
produced with the rules as finally specified: the S6/b schedule, the exact coinbase claim in the
transition block, the replay-protected signature hash (`SIGHASH_FORKID`, fork ID 840), the voluntary
coinbase tag, and no mandatory marker of any kind. It replaces the evidence for `v1.2.0-dev.1`, a build
with an earlier form of replay protection, which remains in the history of this repository.

## Contents

| File | What it holds |
|---|---|
| [`build-manifest.json`](build-manifest.json) | source identity, the two build configurations, toolchains, dependency versions, SHA-256 of every binary |
| [`unit-test-results.md`](unit-test-results.md) | `make check`: commands, counts, the one skip, the 24 test cases added for the transition, the check against real Bitcoin Gold signatures |
| [`functional-test-results.md`](functional-test-results.md) | the functional suite on both builds: counts, baseline failures, skips, the eight new tests and what each establishes, two negative controls |
| [`upgrade-test.md`](upgrade-test.md) | a copy of a running 1.1.0 mainnet node's data directory opened by this build, and by 1.1.0 again |
| [`cross-implementation.md`](cross-implementation.md) | three real implementations against each other on regtest: identities and hashes, what was aligned and how, the patch and its differential check, findings |
| [`cross-implementation-tables.md`](cross-implementation-tables.md) | the generated tables of all 190 recorded verdicts |
| [`cross-implementation-results.json`](cross-implementation-results.json), [`legacy-build-differential-check.json`](legacy-build-differential-check.json) | the raw results |
| [`patches/`](patches/) | the patches applied to the other implementations for testing |
| [`scripts/`](scripts/) | the harness, the differential check, the container wrapper, the table generator |
| [`open-items.md`](open-items.md) | what was not tested, known limitations, the test-suite baseline |

## Summary of results

| What | Result |
|---|---|
| Unit tests (`make check`, development configuration) | passed; 559 test cases, 1 of them a skip |
| Unit tests under ASan and UBSan, and the functional allowlist (166) on a plain build, in the project's CI for the commit the binaries were built from | passed |
| The signature-hash code against real Bitcoin Gold signatures (run with fork ID 79) | a pre-SegWit and a SegWit v0 input of main-chain transactions accepted; rejected with any other fork ID and under the historical rules |
| Functional tests, CI allowlist (166), production configuration | 166 passed |
| Functional tests, CI allowlist (166), development configuration | 166 passed |
| Functional tests, complete base set | 180 passed, 42 skipped, 2 baseline failures |
| Cross-implementation matrix | 190 verdicts, identical in two runs; every expectation of the specification about the other implementations confirmed |
| Offline re-validation of the whole mainnet block chain with full signature checking | all 747,987 blocks (tip `00000004d11d51ec…1ffe34`, 2026-09-20) accepted by the production-configuration binary with `-reindex-chainstate -assumevalid=0`, against the mainnet checkpoints through 744,278, without any network connection, in 22 minutes; no consensus error; the resulting coin supply of 19,112,375 RIN equals the schedule |
| Upgrade in place from 1.1.0 | a copy of a running 1.1.0 mainnet node (height 755,293, `txindex` and block filter index) opened without a reindex: same best block, same UTXO set hash, indexes in sync, `verifychain 4` passed; 1.1.0 opened the same directory again afterwards |
| Reproducibility | the GitHub Actions release build and a local build of the same commit are bit-identical for `rincoind`, `rincoin-cli`, `rincoin-tx` and `rincoin-wallet`; `rincoin-qt` is not |

## Reproducing

The tests are part of the `rincoin-core` source tree (`src/test/s6b_*_tests.cpp`,
`test/functional/feature_s6b_*.py`, `test/functional/wallet_s6b_*.py`, `test/functional/p2p_s6b_relay.py`) and run with
`make check` and `test/functional/test_runner.py`. The cross-implementation harness needs the three
binaries named in [`cross-implementation.md`](cross-implementation.md):

```
python3 scripts/cal_matrix.py --framework <rincoin-core>/test/functional --workdir <empty dir> \
    --out results.json --c-bin <C rincoind> --a-bin <A rincoind or the container wrapper> \
    --l-bin <patched L rincoind> --cli <any rincoin-cli>
python3 scripts/render_matrix.py results.json tables.md
```
