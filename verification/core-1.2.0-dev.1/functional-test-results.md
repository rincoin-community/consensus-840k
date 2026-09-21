# Functional tests

Source tree `03509c310` (branch tip `b9bfeca1d`); builds as in [`build-manifest.json`](build-manifest.json). Dates:
production configuration 2026-09-20, development configuration 2026-09-21. All runs on regtest, on
one Linux host, 16–20 tests in parallel. The production-configuration binaries were built from the
tree before the last commit, which only removed an empty unit test case; built again from the final
tree they are bit-identical (see the manifest).

| Run | Binaries | Result | Wall time |
|---|---|---|---|
| CI allowlist (`test/functional/ci_passing_tests.txt`, 164 tests) | production configuration | **164 passed**, 0 failed, 0 skipped | 911 s |
| CI allowlist | development configuration | **164 passed**, 0 failed, 0 skipped | 650 s |
| complete base set of `test_runner.py` (222 invocations) | development configuration | 178 passed, **42 skipped**, **2 failed** (both are baseline failures, below) | 289 s |

Command: `test/functional/test_runner.py --jobs=16 <the tests of the allowlist>`; the production
binaries were selected with the `BITCOIND` and `BITCOINCLI` environment variables.

**One earlier run failed and is part of the record:** in the first allowlist run on production
binaries of this development line, `feature_abortnode.py` failed (163 of 164). The test deletes an
undo file while the block filter index may still be reading it from its own thread, so the node
aborted in the index instead of in the reorganization the test asserts. This is a race in the test,
not in the node; the test now waits for the index first, passed 6 of 6 repeated runs, and has passed
in every complete run since, including the ones above.

**Baseline failures** (not in the allowlist; identical on the branch before this work):
`feature_signet.py` and `p2p_dos_header_tree.py` stop with `Invalid private key encoding` when the
framework imports its regtest keys into chains that Rincoin does not define that way.

**Skips:** 34 `--descriptors` variants (descriptor wallets are not supported by this code base), and
`feature_assumevalid.py`, `feature_backwards_compatibility.py`, `wallet_upgradewallet.py`,
`mempool_compatibility.py`, `mweb_node_compatibility.py`, `mweb_wallet_address.py`,
`mweb_wallet_upgrade.py` (need binaries of previous releases or are disabled for this fork) and
`rpc_bind.py --ipv6`. A skip is not a pass.

## Tests written for the transition (6, all in the allowlist)

Regtest scales mainnet by 1/1000: the transition height is 840. Durations are those of the allowlist
run on the production configuration.

| Test | Duration | What it establishes |
|---|---|---|
| `feature_s6b_subsidy.py` | 212 s | the schedule before and after the transition and at the later phases (2,100 / 4,200 / 6,300), by real blocks; the transition block at six fee levels (none, ordinary, exactly 0.875 RIN, one base unit above, 1.5 RIN, 25 RIN), each with the exact claim accepted — also split over several outputs — and one base unit less, one more, the claim of the previous schedule, a flat 4 RIN, fees only, and nothing rejected with the right reason; a lower claim valid on both sides of that block; `getblocktemplate` and the node's own miner at that height; over-claims rejected at every phase boundary, including blocks that carry MWEB data; coin supply equal to the schedule; restart, `-reindex-chainstate`, `-reindex`; initial block download by a second node |
| `feature_s6b_sigforkid.py` | 29 s | eight script types (P2PK, P2PKH, bare and P2SH multisig, P2WPKH, P2WSH, P2SH-P2WPKH, P2SH-P2WSH) × six hash types on both sides of the transition: the signature for the other side is refused by the mempool (`new-style-sig-fork-id` / `old-style-sig-fork-id`) and makes a block invalid, the right one is relayed to a second node and mined there; Taproot key-path spends with all seven hash types unchanged; at the boundary, historical transactions and their descendants leave the mempool on both nodes while signature-free and Taproot transactions stay and block templates remain valid; a wallet transaction pending at the boundary (abandon, send again); a reorganization across the boundary in both directions |
| `feature_s6b_sighash_single.py` | 13 s | `SIGHASH_SINGLE` without a matching output through real block validation, 72 cases per side: the historically valid signature over the constant digest, garbage signatures, scripts ending in `OP_NOT`, `OP_CHECKSIG(VERIFY)`, `OP_CHECKMULTISIG(VERIFY)`, 2-of-2 with a good first signature, with and without `ANYONECANPAY`, bare and P2SH — all accepted or rejected as ever below the transition height, all a script error from it on; unchanged neighbors (matching output, other hash types, empty signatures, P2WSH, Taproot); mempool and signing RPC agree; a spend confirmed in the last block below the transition stays valid through restart and `-reindex`, the same kind of spend left in the mempool is removed and can no longer be mined |
| `wallet_s6b_signing.py` | 77 s | on both sides: wallet sends from legacy, P2SH-SegWit and bech32 coins, `signrawtransactionwithwallet`, `signrawtransactionwithkey`, a single-signer PSBT, two parties signing a 2-of-2 one after the other, two parties signing independently and `combinerawtransaction`, two wallets signing a multisig PSBT independently with `combinepsbt`, `analyzepsbt` and `finalizepsbt`; a raw transaction and a PSBT signed before the transition and not confirmed in time are refused afterwards, signing again makes them valid |
| `feature_s6b_coinbase_flags.py` | 11 s | the `/RCC/` tag in `getblocktemplate` and in mined blocks (after the BIP34 height and the extra nonce, within 100 bytes, with the witness commitment) below, at and above the transition height; coinbases as pool software builds them, with the flags copied raw, wrapped in one push, ignored, or replaced by a pool's own tag; blocks with the commitment output of earlier testing builds (once, twice, other payload) and with block version `0x52494e33` are judged by the ordinary rules only; the ordinary rules still hold (scriptSig length, BIP34 height) |
| `feature_s6b_reorg.py` | 15 s | two nodes mine competing branches across the transition height and the shorter side reorganizes: its transactions signed for the new side return to the mempool, the one confirmed below the transition on the abandoned branch has to be made again, the coin supply matches the schedule; a branch with more blocks whose transition block claims the previous schedule's subsidy is announced by a peer and rejected, also after restart and `-reindex`, and by a node that is still below the transition height |

`feature_s6b_sighash_single.py` was also run against a deliberately weakened node in which the rule
only makes the signature check fail instead of raising a script error: the test fails, and a probe
spend of a `CHECKSIG NOT` output with a garbage `SIGHASH_SINGLE` signature above the transition
height is accepted by the weakened node and rejected by the real one.

`wallet_s6b_signing.py` was additionally run against a build in which signatures made by another
party are checked with the historical signature hash only: it fails at the first multi-party step
above the transition height, which shows that the multi-party cases really depend on the regime
being passed to the checking side (raw transactions, `combinerawtransaction`, `finalizepsbt`,
`analyzepsbt`, the GUI). The same is pinned by unit tests.

## Existing tests adapted to the new regtest parameters

`feature_block.py` (its large reorganization crosses height 840: transactions sign for the
confirming height, the transition block claims its fees exactly), `feature_taproot.py` (pre-Taproot
spends sign for the confirming height; from 840 a pre-SegWit `SIGHASH_SINGLE` input always gets a
matching output), `mining_basic.py`, `rpc_blockchain.py`, `rpc_createmultisig.py`,
`rpc_dumptxoutset.py` (vectors regenerated: the coinbase tag changes coinbase transaction IDs),
`feature_min_peer_proto_floor.py` (floor at 840), the MWEB tests (MWEB active from 2,448), and the
tests that must work with both a pre-release and a release build (`feature_config_args.py`,
`feature_uacomment.py`, the `rincoin-tx` utility tests).

## Validation of the existing chain

The production-configuration binary re-validated the whole mainnet block chain offline
(`-reindex-chainstate -assumevalid=0 -connect=0`, no network connections, no wallet): see the README
of this directory for the result. The development build never connected to the public network.
