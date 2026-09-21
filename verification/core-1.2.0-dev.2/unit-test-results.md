# Unit tests

Build: development configuration (see [`build-manifest.json`](build-manifest.json)), source tree
`7924b96b3` (branch tip `b7bc1a9ef`). Date: 2026-09-21.

| Command | Result | Duration |
|---|---|---|
| `make -k -j40 check` | exit code 0: all 127 per-file runs of `test_rincoin` passed, as did the GUI tests (`test_rincoin-qt`), the secp256k1-zkp tests (`tests`, `exhaustive_tests`), the UniValue tests and the `rincoin-tx` utility test vectors | 137 s |
| `src/test/test_rincoin` (one process, all suites) | 555 test cases: 554 passed, 1 skipped itself with a warning; 8,866,551 assertions, none failed (the number varies between runs because some suites are randomized) | 91 s |

The skipped case is `script_tests/script_assets_test`. It needs the optional upstream asset file
(`DIR_UNIT_TEST_DATA` unset), reports that as a warning and does nothing; this is the same on the
branch before this work. It is a skip, not a pass.

One case was removed. `blockfilter_tests/blockfilters_json_test` had an empty body from version 1.0.5
on (its BIP158 vectors are built from Bitcoin blocks) and was counted as passed without checking
anything.

## Test cases added for the transition (21)

| Suite | Cases | What they pin |
|---|---|---|
| `s6b_subsidy_tests` | 5 | `GetBlockSubsidy` against the frozen normative vectors of the S6/b specification (`analysis/data/S6B_normative_test_vectors.csv`), the ceiling of exactly 168,000,000 RIN, every phase boundary, unchanged history below the transition, and the scaled schedules of testnet, preview and regtest. Expected values come from the vectors and from arithmetic in the test, never from the function under test |
| `s6b_transition_block_tests` | 1 | real block connection on regtest: at height 840 only the exact claim connects (`bad-cb-amount-transition` one base unit lower, `bad-cb-amount` one higher); at 839 and 841 a lower claim connects |
| `s6b_sighash_tests` | 7 | the constants as implementers see them (flag `0x40`, fork ID 840, the preimage of a `SIGHASH_ALL` signature ending in `41 48 03 00`, the combined value `0x00034840`); 144 known-answer digests for both script versions, every hash type with and without the flag, on both sides of the transition, produced by an independent Python implementation (`test/util/gen_s6b_sighash_vectors.py`); **signatures of two real Bitcoin Gold main-chain transactions** (a pre-SegWit input, block 965,449, and a SegWit v0 input, block 965,232), which the interpreter accepts when it runs with Bitcoin Gold's fork ID 79, through `SignatureHash`, ECDSA verification and `VerifyScript` with consensus and with standard flags, and rejects with fork ID 840, with fork ID 0 and under the historical rules; what the digest depends on (regime, flag, fork ID, amount; the same digest for both script versions); every evaluated signature must set the flag, a script error in all four opcodes, also behind `OP_NOT`, in 2-of-2 multisig and in P2WSH, while empty and failing flagged signatures stay ordinary failed checks; below the transition a hash type byte with bit `0x40` means what it always meant, and the standardness rule follows the regime; `SIGHASH_SINGLE` without a matching output on both sides |
| `s6b_sign_tests` | 8 | the signing side: the signature creator adds the flag and signs the new digest where the regime is in force, and never produces the flag outside it; `SignTransaction` verifies what it signed under the same rule and needs the amount of every input there (`Missing amount`); omitted arguments mean the historical behavior; a co-signer's signature is recognized only under the rule it was made for (`DataFromTransaction`); two parties signing one after the other complete a multisig input on both sides of the transition; a combined PSBT finalizes under the right rule and only under it |

The `rincoin-tx` utility tests (part of `make check`) gained five vectors for `-signheight`: the
historical signature below the transition height, the replay-protected one at it (both outputs were
verified with two independent implementations before they were stored), the hash type named
explicitly, and the two errors (an output without its amount; a `FORKID` hash type without a height
at or above the transition).

Existing tests adapted to the new test-network parameters: `validation_tests` (subsidy sums for the
210 and 2,100 intervals), `miner_tests`, `script_tests` (error table), `rinhash_tests` (the peer
protocol floor now rises at each network's transition height) and `versionbits_tests` (the start and
timeout heights of every deployment are multiples of the version-bits window on every network, the
start is below the timeout, and the preview network is checked as well).
