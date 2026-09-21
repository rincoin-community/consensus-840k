# Unit tests

Build: development configuration (see [`build-manifest.json`](build-manifest.json)), source tree
`03509c310` (branch tip `b9bfeca1d`). Date: 2026-09-21.

| Command | Result | Duration |
|---|---|---|
| `make -k -j40 check` | exit code 0: all 127 per-file runs of `test_rincoin` passed, as did the GUI tests (`test_rincoin-qt`), the secp256k1-zkp tests (`tests`, `exhaustive_tests`), the UniValue tests and the `rincoin-tx` utility test vectors | 130 s |
| `src/test/test_rincoin` (one process, all suites) | 551 test cases: 550 passed, 1 skipped itself with a warning; 9,045,205 assertions, none failed (the number varies between runs because some suites are randomized) | 89 s |

The skipped case is `script_tests/script_assets_test`. It needs the optional upstream asset file
(`DIR_UNIT_TEST_DATA` unset), reports that as a warning and does nothing; this is the same on the
branch before this work. It is a skip, not a pass.

One case was removed. `blockfilter_tests/blockfilters_json_test` had an empty body from version 1.0.5
on (its BIP158 vectors are built from Bitcoin blocks) and was counted as passed without checking
anything.

## Test cases added for the transition (18)

| Suite | Cases | What they pin |
|---|---|---|
| `s6b_subsidy_tests` | 5 | `GetBlockSubsidy` against the frozen normative vectors of the S6/b specification (`analysis/data/S6B_normative_test_vectors.csv`), the ceiling of exactly 168,000,000 RIN, every phase boundary, unchanged history below the transition, and the scaled schedules of testnet, preview and regtest. Expected values come from the vectors and from arithmetic in the test, never from the function under test |
| `s6b_transition_block_tests` | 1 | real block connection on regtest: at height 840 only the exact claim connects (`bad-cb-amount-transition` one base unit lower, `bad-cb-amount` one higher); at 839 and 841 a lower claim connects |
| `s6b_sighash_tests` | 5 | the 16-byte constant; 72 known-answer vectors for the legacy and BIP143 digests with and without the identifier, produced by an independent Python implementation (`test/util/gen_s6b_sighash_vectors.py`); every hash type changes; `SIGHASH_SINGLE` without a matching output is a script error when active, in `OP_CHECKSIG` and `OP_CHECKMULTISIG`, also behind `OP_NOT`; the neighboring cases are unchanged |
| `s6b_sign_tests` | 7 | the signing side: the signature creator mixes the identifier in; `SignTransaction` verifies what it signed under the same rule; omitted arguments mean the historical behavior; no `SIGHASH_SINGLE` signature is produced for an input without a matching output; a co-signer's signature is recognized only under the rule it was made for (`DataFromTransaction`); two parties signing one after the other complete a multisig input on both sides of the transition; a combined PSBT finalizes under the right rule and only under it |

Existing tests adapted to the new test-network parameters: `validation_tests` (subsidy sums for the
210 and 2,100 intervals), `miner_tests`, `script_tests` (error table), `rinhash_tests` (the peer
protocol floor now rises at each network's transition height) and `versionbits_tests` (the start and
timeout heights of every deployment are multiples of the version-bits window on every network, the
start is below the timeout, and the preview network is checked as well).
