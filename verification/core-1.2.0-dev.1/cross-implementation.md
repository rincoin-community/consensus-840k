# Three implementations against each other — method and findings

Date of the runs: 2026-09-20. Result tables: [`cross-implementation-tables.md`](cross-implementation-tables.md)
(generated from [`cross-implementation-results.json`](cross-implementation-results.json) by
[`scripts/render_matrix.py`](scripts/render_matrix.py)).

This is an end-to-end test of real node software. Three implementations run side by side on one
private regtest chain; each mines with its own miner and pays with its own wallet; every verdict in
the tables is what the validating node itself answered. Nothing here ran on, or was connected to,
a public network.

## The three implementations

| | What | Source identity | Binary used |
|---|---|---|---|
| **C** | Rincoin Community Core 1.2.0, development build `v1.2.0-dev.1` | see [`build-manifest.json`](build-manifest.json) | the production-configuration build, `rincoind` SHA-256 `ceccfb491503bb50805125152d51019e48a784c3761d743cfc758053933628a8` |
| **A** | Rin-coin/rincoin `v1.1.0-rc1` | `https://github.com/Rin-coin/rincoin`, tag `v1.1.0-rc1` → commit `a1b12dc8c332677c1fb8b3dbf32ca91f258f6d59`. On 2026-09-20 this was both the newest (pre)release and the head of its `v1.1` branch | the **unmodified official release binary**: `bin/rincoind` from `rincoin-1.1.0rc1-x86_64-linux-gnu.tar.gz` (archive SHA-256 `2e5303e384a4822f0ea250df85a64062ac58f65b6fff91bf182bbd291dee3e42`, as listed in the release's `SHA256SUMS`; the detached signature was not verified), binary SHA-256 `b1f800a270aeed85c52e3c76d55d3c0b8027229d174748197d91eb1dcfc065d3`. It is linked against Ubuntu 24.04 libraries, so it ran inside an Ubuntu 24.04 container with host networking ([`scripts/rincoind-in-container.sh`](scripts/rincoind-in-container.sh)) |
| **L** | the unchanged schedule: Rin-coin/rincoin version 1.0.5 | `https://github.com/Rin-coin/rincoin`, `master` → commit `b52c87778f800dc5f4e2f59c372badbc139f933f` (reports itself as 1.0.5; that repository has no `v1.0.5` tag, and the tree is identical to the `v1.0.5` tag of `rincoin-community/rincoin-core`) | built from that commit **with a one-line patch** (below), `rincoind` SHA-256 `356c41713967f2637cfb95dbdf8d48ce9a6321008fbfec9ae0cab72fa8d6d336` |

Two different projects have published something called 1.1.0: the `v1.1.0-rc1` above, and the
`v1.1.0` maintenance line of Rincoin Community Core, which changes no consensus rule and is not part
of this comparison.

## What had to be aligned, and how

All three share the regtest genesis block
(`7d2c8c57ce2597f86c9fe41f9865ad664b04d2aad4321fdaab48ed3da1805fe7`), the regtest message start
(`72 72 63 74`), the port and the address formats, so they can exchange blocks, transactions and
P2P connections directly. Two things differ on regtest:

1. **Halving interval.** C and A use 210 blocks on regtest, so their transition is at height 840
   and the subsidy before it is 6.25 RIN, exactly as on mainnet before 840,000. The 1.0.5 source
   uses 150, which would put its own fourth halving at height 600. No command-line option changes
   that, so L was built with
   [`patches/rin-coin-rincoin-v1.0.5-regtest-interval.patch`](patches/rin-coin-rincoin-v1.0.5-regtest-interval.patch)
   (`nSubsidyHalvingInterval` 150 → 210 in `CRegTestParams`, nothing else). With it L pays 6.25 RIN
   at height 839 and 3.125 RIN at height 840: the mainnet situation at 839,999 / 840,000.
2. **MWEB activation.** C activates MWEB on regtest by height (active from 2,448); A and L by time
   (active from 432), after which their blocks carry MWEB data. All tests here are below height
   900, so A and L were started with the regtest-only option `-vbparams=mweb:0:0:2160:2304`, which
   gives them C's schedule. No source change is involved.

A was **not** patched for these runs. (A patch that rescales A's *testnet* to Community Core's
testnet parameters was prepared as well,
[`patches/rin-coin-rincoin-v1.1.0-rc1-testnet-scale.patch`](patches/rin-coin-rincoin-v1.1.0-rc1-testnet-scale.patch);
a build with it gave the same 190 regtest results as the official binary, and no testnet run was
made.)

**Is the patched L still L?** [`scripts/l_authenticity.py`](scripts/l_authenticity.py) ran the patched
build against an unmodified 1.0.5 release build (SHA-256
`aea74ce203dfd805e45e5a41a42f9d2dac2d8cc96b666c7e817517bce86d346c`):
the patched build accepts the unmodified build's first 149 blocks, including a wallet transaction;
at height 150 they differ exactly as the patch says (the unmodified build pays 25 RIN and rejects a
50 RIN block with `bad-cb-amount`; the patched build pays 50 RIN and accepts the 25 RIN block); and
the unmodified build's own fourth halving (6.25 → 3.125 RIN at height 600) pays what the patched
build pays at 839 → 840. Result: [`legacy-build-differential-check.json`](legacy-build-differential-check.json),
5 of 5 checks passed.

What this setup does not show: the behavior of any implementation on its own test network or on
mainnet parameters, and anything that depends on real proof-of-work competition. "More work" below
always means a controlled number of regtest blocks at minimum difficulty, never hash rate.

## How verdicts were obtained

- **Blocks.** The producer mines with `generatetoaddress`, that is, with its own block assembler and
  the full reward its `getblocktemplate` would offer. The raw block goes to the validator through
  `submitblock`; the answer (`null` = accepted; `inconclusive` = valid but on a side branch; anything
  else = the reject reason) is recorded verbatim. Validators start from a copy of the same chain
  (835 blocks mined by L and accepted by C and A), so a verdict is never influenced by an earlier
  scenario.
- **Transactions.** The producer's wallet makes an ordinary payment (`sendtoaddress`). Each
  validator judges it twice on its own valid chain at the same height: `testmempoolaccept` (policy
  and consensus) and `generateblock` with that transaction (consensus only). This separates
  transaction compatibility from the fate of whole blocks.
- **Manipulated blocks** are built by the test, not by any miner, and are reported separately.
- **Peers.** Manual outbound connections (`addnode … onetry`), checked after four seconds.

The harness is [`scripts/cal_matrix.py`](scripts/cal_matrix.py). The matrix was run four times: with
a locally built A and a development-configuration C, with the official A binary and the same C, and
twice with the official A binary and a production-configuration C (the build recorded here and an
earlier build of the same development line). All 190 recorded verdicts were identical in all four
runs; the tables show the last one.

## Findings

Regtest heights; read 840 as mainnet 840,000.

1. **Below the transition height all three agree.** Each accepts the others' blocks (heights
   836–839) and transactions, in the mempool and in blocks. A reorganization among them is ordinary:
   A, holding its own transaction in a one-block branch, switches to a longer empty branch mined by
   C; the transaction loses its confirmation and waits in A's mempool (scenario 4).
2. **The block at the transition height.**

   | Mined by ↓ / judged by → | C | A | L |
   |---|---|---|---|
   | C (4 RIN, coinbase tag `/RCC/`) | valid | accepted | rejected, `bad-cb-amount` |
   | A (4 RIN) | accepted | valid | rejected, `bad-cb-amount` |
   | L (3.125 RIN) | rejected, `bad-cb-amount-transition` | **accepted** | valid |

   C and A accept each other's empty blocks and stay on one chain while blocks are empty. A accepts
   L's block 840, because for A a lower claim is always valid, and then mines its own 4 RIN block
   841 on top of it (scenario 6); C rejects that block and everything after it for its ancestor.
   The exact-claim rule of C is what makes the legacy block 840 invalid for C.
3. **An invalid ancestor is never outweighed.** Six empty descendants of the rejected block 840,
   more than C's own chain had, are all rejected (`bad-prevblk`, `prev-blk-not-found`), and so is a
   hand-built child that satisfies every rule on its own (scenario 7).
4. **The first ordinary transaction separates C and A.** C's block with a C transaction is rejected
   by A (`bad-tx-rinhash-version`: the transaction does not carry A's required version). A's block
   with an A transaction is rejected by C (the signature does not verify under C's signature hash).
   After that each rejects the other's later blocks for their ancestor.
5. **Transactions across the three** (above the transition height):

   | Made by ↓ / judged by → | C | A | L |
   |---|---|---|---|
   | C | valid | mempool and block: `bad-tx-rinhash-version` | mempool and block: signature invalid |
   | A | mempool: `old-style-sig-fork-id`; block: signature invalid | valid | mempool: `version` (standardness); **block: accepted** |
   | L | mempool: `old-style-sig-fork-id`; block: signature invalid | mempool and block: `bad-tx-rinhash-version` | valid |

   C's transactions are invalid for both others at the consensus level, and theirs for C. A's
   transactions are kept out of L's mempool only by a standardness rule; a block that contains one
   is valid for L.
6. **The signature rule is not a checkpoint.** C, with its own transaction confirmed at 841, switches
   to a longer branch of empty A blocks (840–843); the transaction returns to C's mempool, and C
   confirms it again in its next block, 844, which A rejects (scenario 5).
7. **Manipulated blocks at 840.** Every validator rejects a claim above its own maximum. A block
   claiming one base unit less than 4 RIN is rejected by C (`bad-cb-amount-transition`), accepted by
   A, and rejected by L (it is above 3.125 RIN). A block version of `0x52494e33` changes nothing for
   anybody: A's rule is about transaction versions, not block versions.
8. **Peers.** Below the transition height every manual connection holds. Above it, C and L no longer
   connect in either direction (C requires protocol version 70018 from that height; L announces
   70017); every connection with A holds. A announces an additional service bit (2^25). That A's
   *automatic* outbound peer selection requires that bit was read in A's source and not tested.
