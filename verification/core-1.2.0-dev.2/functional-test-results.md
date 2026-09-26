# Functional tests

Sources of the branch tip in [`build-manifest.json`](build-manifest.json); the production binaries are
the GitHub Actions release build described there. Date: 2026-09-26. All runs on regtest, on one Linux
host, 12–20 tests in parallel.

| Run | Binaries | Result | Wall time |
|---|---|---|---|
| CI allowlist (`test/functional/ci_passing_tests.txt`, 166 tests) | production configuration | **166 passed**, 0 failed, 0 skipped | 933 s |
| CI allowlist | development configuration | **166 passed**, 0 failed, 0 skipped | 944 s |
| CI allowlist, the project's CI for the commit the binaries were built from | its own plain build | **passed** | |
| complete base set of `test_runner.py` (224 invocations) | development configuration, one commit earlier (the MWEB change below does not touch regtest) | 180 passed, **42 skipped**, **2 failed** (both are baseline failures, below) | 291 s |

A first run of the allowlist on the production binaries of the previous commit had one failure, `feature_s6b_subsidy.py`:
after a restart with `-reindex` it waited longer than the framework's 60 seconds for the mempool to
load. That run shared the host with the upgrade test and the offline re-validation of mainnet (both
below), which read gigabytes at the same time. The same binaries passed the test in every other run,
including the complete allowlist again on an otherwise idle host, which is the result in the table.

Command: `test/functional/test_runner.py --jobs=16 <the tests of the allowlist>`; the production
binaries were selected with the `BITCOIND` and `BITCOINCLI` environment variables.

**Baseline failures** (not in the allowlist; identical on the branch before this work):
`feature_signet.py` and `p2p_dos_header_tree.py` stop with `Invalid private key encoding` when the
framework imports its regtest keys into chains that Rincoin does not define that way.

**Skips:** 34 `--descriptors` variants (descriptor wallets are not supported by this code base), and
`feature_assumevalid.py`, `feature_backwards_compatibility.py`, `wallet_upgradewallet.py`,
`mempool_compatibility.py`, `mweb_node_compatibility.py`, `mweb_wallet_address.py`,
`mweb_wallet_upgrade.py` (need binaries of previous releases or are disabled for this fork) and
`rpc_bind.py --ipv6`. A skip is not a pass.

## Tests written for the transition (8, all in the allowlist)

Regtest scales mainnet by 1/1000: the transition height is 840. Durations are those of the allowlist
run on the production configuration.

| Test | Duration | What it establishes |
|---|---|---|
| `feature_s6b_subsidy.py` | 229 s | the schedule before and after the transition and at the later phases (2,100 / 4,200 / 6,300), by real blocks; the transition block at six fee levels (none, ordinary, exactly 0.875 RIN, one base unit above, 1.5 RIN, 25 RIN), each with the exact claim accepted — also split over several outputs — and one base unit less, one more, the claim of the previous schedule, a flat 4 RIN, fees only, and nothing rejected with the right reason; a lower claim valid on both sides of that block; `getblocktemplate` and the node's own miner at that height; over-claims rejected at every phase boundary, including blocks that carry MWEB data; coin supply equal to the schedule; restart, `-reindex-chainstate`, `-reindex`; initial block download by a second node |
| `feature_s6b_sigforkid.py` | 40 s | eight script types (P2PK, P2PKH, bare and P2SH multisig, P2WPKH, P2WSH, P2SH-P2WPKH, P2SH-P2WSH) × six hash types on both sides of the transition: the signature for the other side is refused by the mempool (`new-style-sig-fork-id` / `old-style-sig-fork-id`) and makes a block invalid (below the transition height a replay-protected signature simply does not verify; from it a historical one is the script error `Signature must use SIGHASH_FORKID`), the right one is relayed to a second node and mined there; Taproot key-path spends with all seven hash types unchanged; at the boundary, historical transactions and their descendants leave the mempool on both nodes while signature-free and Taproot transactions stay and block templates remain valid; a wallet transaction pending at the boundary (abandon, send again); a reorganization across the boundary in both directions; a transaction carrying the version marker `0x52494e33` that another implementation requires, with signatures for this chain: relay policy refuses it as non-standard, a block carrying it is valid, and the marker does nothing for a signature made for the other side |
| `feature_s6b_sighash_single.py` | 17 s | `SIGHASH_SINGLE` without a matching output through real block validation, 98 cases per side: the historically valid signature over the constant digest, with and without bit `0x40` in its hash type, garbage signatures, scripts ending in `OP_NOT`, `OP_CHECKSIG(VERIFY)`, `OP_CHECKMULTISIG(VERIFY)`, 2-of-2 with a good first signature, with and without `ANYONECANPAY`, bare, P2SH and P2WSH. Below the transition height all of it is accepted or rejected as ever; from it every signature without the flag is a script error whatever follows the opcode, the signature over the constant digest with the flag added is just a signature that does not verify, and a real replay-protected `SIGHASH_SINGLE` signature is an ordinary one; empty signatures, failing flagged signatures under `OP_NOT` and Taproot behave as before; mempool and signing RPC agree; a spend confirmed in the last block below the transition stays valid through restart and `-reindex`, the same kind of spend left in the mempool is removed and can no longer be mined |
| `wallet_s6b_signing.py` | 142 s | on both sides: wallet sends from legacy, P2SH-SegWit and bech32 coins, `signrawtransactionwithwallet`, `signrawtransactionwithkey`, the hash type the node produces (`[ALL]` below, `[ALL\|FORKID]` from the transition height) and accepts (`FORKID` names are an error below it), the amount a pre-SegWit `prevtxs` entry needs from the transition height (`Missing amount`), a single-signer PSBT, two parties signing a 2-of-2 one after the other, two parties signing independently and `combinerawtransaction`, two wallets signing a multisig PSBT independently with `combinepsbt`, `analyzepsbt` and `finalizepsbt`; a raw transaction and a PSBT signed before the transition and not confirmed in time are refused afterwards, signing again makes them valid |
| `feature_s6b_coinbase_flags.py` | 12 s | the `/RCC/` tag in `getblocktemplate` and in mined blocks (after the BIP34 height and the extra nonce, within 100 bytes, with the witness commitment) below, at and above the transition height; coinbases as pool software builds them, with the flags copied raw, wrapped in one push, ignored, or replaced by a pool's own tag; blocks with the commitment output of earlier testing builds (once, twice, other payload) and with block version `0x52494e33` are judged by the ordinary rules only; the ordinary rules still hold (scriptSig length, BIP34 height) |
| `wallet_s6b_boundary.py` | 37 s | the paths where building a transaction and signing it are separate steps, on both sides: `fundrawtransaction` then `signrawtransactionwithwallet`, `walletcreatefundedpsbt` then `walletprocesspsbt` and `finalizepsbt`, `send`, `bumpfee`, each checked for the hash type it signed with and for reaching a block; the exact block at which the wallet switches (at tip 838 it still signs the historical way, at tip 839 already for the transition block); a PSBT funded below the height and signed above it, which works because the regime is chosen at signing; a restart with `-rescan` across the height; a transaction still unconfirmed at the height, kept out of the blocks before it by fee so that afterwards only the transition rule keeps it out: it leaves the mempool of both nodes, and the same coins can be spent again at once |
| `p2p_s6b_relay.py` | 7 s | a peer that relays a transaction signed for the other side is refused with `old-style-sig-fork-id` and not punished: no misbehaviour score, the connection stays; checked twice, after a new block and on a new connection, because the node forgets rejected transactions when the tip moves and remembers what a peer announced only per connection |
| `feature_s6b_reorg.py` | 16 s | two nodes mine competing branches across the transition height and the shorter side reorganizes: its transactions signed for the new side return to the mempool, the one confirmed below the transition on the abandoned branch has to be made again, the coin supply matches the schedule; a branch with more blocks whose transition block claims the previous schedule's subsidy is announced by a peer and rejected, also after restart and `-reindex`, and by a node that is still below the transition height |

Two negative controls, each against a deliberately weakened node binary:

- In the first, a signature without `SIGHASH_FORKID` is not a script error from the transition
  height on; its check merely fails. `feature_s6b_sighash_single.py` fails against it. A probe shows
  what the difference means: above the transition height a spend of a `<key> OP_CHECKSIG OP_NOT`
  output with a garbage signature that lacks the flag is accepted by the weakened node and
  rejected by the real one (`Signature must use SIGHASH_FORKID`).
- In the second, signatures made by another party are looked at without the regime of the
  confirming block. `wallet_s6b_signing.py` passes everything below the transition height and fails
  at the first multi-party step above it, which shows that the multi-party cases really depend on
  the regime being passed to the checking side (raw transactions, `combinerawtransaction`,
  `finalizepsbt`, `analyzepsbt`, the GUI). The same is pinned by unit tests.

## Existing tests adapted to the new regtest parameters

`feature_block.py` (its large reorganization crosses height 840: transactions sign for the
confirming height, the transition block claims its fees exactly), `feature_taproot.py` (pre-Taproot
spends sign for the confirming height; its random undefined hash types avoid the ones that
`SIGHASH_FORKID` makes defined from 840), `mining_basic.py`, `rpc_blockchain.py`, `rpc_createmultisig.py`,
`rpc_dumptxoutset.py` (vectors regenerated: the coinbase tag changes coinbase transaction IDs),
`feature_min_peer_proto_floor.py` (floor at 840), the MWEB tests (MWEB active from 2,448), and the
tests that must work with both a pre-release and a release build (`feature_config_args.py`,
`feature_uacomment.py`, the `rincoin-tx` utility tests).

## Validation of the existing chain

The production-configuration binary re-validated the whole mainnet block chain offline
(`-reindex-chainstate -assumevalid=0 -connect=0`, no network connections, no wallet), against the
mainnet checkpoints that now run to block 744,278: see the README of this directory for the result.
It also opened a copy of the data directory of a running 1.1.0 mainnet node and handed it back to
1.1.0: [`upgrade-test.md`](upgrade-test.md). The development build never connected to the public
network.
