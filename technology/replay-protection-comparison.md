# Transaction Replay Protection at Height 840,000 — Comparison of the Two Current Mechanisms

Status: Technical comparison — not a consensus document (complements the 2026-08-16 assessment
[`response-to-rip-0009.md`](response-to-rip-0009.md), which remains published; this document
compares the two mechanisms against the code as released)

Date: 2026-09-21 (first version 2026-09-19; the behavior observed when the three implementations
were run against each other was added on 2026-09-20, [§5](#5-observed-behavior); this version
follows Revision 6.0 of the specification, in which Community Core's mechanism has the
`SIGHASH_FORKID` form)

Two Rincoin implementations plan to change the rules at mainnet height 840,000, and each uses a
different mechanism to keep ordinary transactions from being valid on both continuations:

- **Rincoin Community Core 1.2.0** (rincoin-community/rincoin-core, in development) changes the
  signature hash of every pre-SegWit and SegWit v0 input from height 840,000 to the replay-protected
  form of Bitcoin Cash and Bitcoin Gold: the signature sets `SIGHASH_FORKID`, the digest is the
  BIP143 one for every input, and the hash type in the preimage carries the fork ID 840 — see
  [`consensus-transition.md §5`](consensus-transition.md#5-transaction-replay-protection-sighash_forkid).
- **Rin-coin/rincoin v1.1.0-rc1** (tag `v1.1.0-rc1`, commit `a1b12dc8c332677c1fb8b3dbf32ca91f258f6d59`,
  published 2026-09-15 by its maintainer, Aevust) requires every non-coinbase transaction in a block
  at height ≥ 840,000 to carry `nVersion = 0x52494e33` (ASCII "RIN3"); the signature hash is
  unchanged. Its author's design rationale is published as RIP-0009 in the `Aevust/rincoin-rips`
  repository; this comparison refers to the code as released.

Both implementations use the same subsidy path from 840,000 (4 → 2 → 1 → 0.6 RIN); the differences
that matter for a common chain are listed in [§4](#4-other-rule-differences-between-the-two-implementations).

## 1. How each mechanism works, as implemented

**RIN3 (Rin-coin/rincoin v1.1.0-rc1):**

- Consensus: `ContextualCheckBlock` rejects a block at height ≥ `nRinHashForkHeight` (840,000 on
  mainnet) if any transaction other than the coinbase, the MWEB HogEx, or an MWEB-only transaction
  has `nVersion != 0x52494e33` (`src/validation.cpp`, reject reason `bad-tx-rinhash-version`).
- Mempool: the same check runs at mempool admission against the next block height, classified as
  `TX_RECENT_CONSENSUS_CHANGE` so that peers relaying such transactions are not penalized
  (`MemPoolAccept::PreChecks`; commit `9426ca366`, 2026-08-26).
- Block assembly: `BlockAssembler::TestPackageTransactions` skips packages containing a
  legacy-version transaction, so a stale mempool entry cannot invalidate a template.
- Standardness: `IsStandardTx` accepts `0x52494e33` in addition to versions 1 and 2.
- Wallet: new transactions carry the RIN3 version once the wallet's last processed height is
  ≥ 839,999 (one block before activation).
- Networking: service bit `NODE_RIN3` (bit 25) is advertised and required for outbound peer
  selection; `PROTOCOL_VERSION` is 70018; no minimum peer version floor is raised.

**`SIGHASH_FORKID` with fork ID 840 (Rincoin Community Core 1.2.0):**

- Consensus: from height 840,000 every evaluated ECDSA signature must set `SIGHASH_FORKID`
  (a script error otherwise) and is hashed with the BIP143 algorithm, pre-SegWit inputs included,
  with the fork ID in the upper three bytes of the hash type that ends the preimage.
- Mempool: transactions are checked against the regime of the next block; historical-style
  signatures after the boundary are reported as a recent consensus change, not as misbehavior;
  stale entries are evicted when the boundary is crossed.
- Block assembly: the mempool contains only transactions valid for the next block, so templates
  are unaffected; the template validity check in Core covers the remainder.
- Standardness and transaction format: unchanged (`nVersion` 1 or 2); the hash-type byte of a
  signature has the additional flag.
- Wallet, raw-transaction RPCs, PSBT and `rincoin-tx` sign for the next block's regime.
- Networking: no service bit; the pre-existing per-height minimum peer version schedule applies.

## 2. Technical comparison

**Separation from the unchanged rules is one-directional with RIN3 and two-directional with a
sighash change.** A transaction carrying `nVersion = 0x52494e33` is rejected by the new rule's
mempool only for the *other* direction; toward the unchanged rules nothing rejects it: unchanged
consensus accepts any `nVersion` in a block. Unchanged *policy* (`IsStandardTx`) does refuse
versions above 2 in the mempool, so such a transaction would normally not be relayed by unchanged
nodes, but a miner can include it in a block through its own template or a modified policy. The
protection toward the unchanged rules is therefore a standardness property, not a consensus
property. A replay-protected signature is invalid under the unchanged rules at the
consensus level, and a historical signature is invalid under the new rules at the consensus level;
neither direction depends on relay policy or on the other implementation's cooperation.

**`nVersion` is part of the signed data.** Under both the legacy and the BIP143 preimage the
transaction version is signed, so a finished signed transaction cannot be re-labelled with a
different version while keeping its signature. The weakness described above is not "rewrite the
version"; it is that an already-signed RIN3 transaction is acceptable under the unchanged rules
wherever a block includes it.

**A permanently required magic version value constrains the field.** Requiring `0x52494e33` in
every ordinary transaction for the rest of the chain's life removes the transaction version from
its ordinary use for format evolution and version-conditioned behavior (as BIP68 uses version 2).
Any later change would have to redefine this rule explicitly. This does not mean `nVersion` can
never be used to change rules, only that every future use must first replace the constant
requirement.

**Compatibility surface.** Both mechanisms require every signing or transaction-constructing
component to change, but in different places:

| Component | RIN3 | `SIGHASH_FORKID` |
|---|---|---|
| Wallets and libraries that build transactions | must set `nVersion = 0x52494e33` | must sign the Bitcoin Gold way with the fork ID 840; software that supports Bitcoin Gold or Bitcoin Cash has the construction, some of it by configuration |
| Software that only signs a prepared transaction (PSBT signers, hardware wallets) | unaffected if the version is already set | must produce the new signatures and know the amount of every input; the generic coin definitions of hardware wallets express the form (as for Bitcoin Gold), none supports Rincoin today |
| Indexers, explorers, relays | may need to accept version `0x52494e33` where they validate standardness themselves | unaffected |
| Mining software and pools | unaffected | unaffected |
| Fee estimation, RBF signalling | unaffected (BIP125 uses `nSequence`, not `nVersion`) | unaffected |

Claims that "all indexers" or RBF depend on `nVersion` in one specific way are not supported by the
code reviewed; the assessment above is per component. The signature-hash approach places its cost
on every signer, including external and offline ones; that cost is real, it is why the
specification is published ahead of the release, and it is why the form chosen is one that has been
in use since 2017 and that existing software already implements.

**Bundling.** In Rin-coin/rincoin the activation height of RIN3 is asserted to equal
`4 × nSubsidyHalvingInterval`, the same height as its subsidy change. Community Core's
signature rule is a separate rule that happens to activate at the same height; either rule could be
reviewed or replaced on its own.

**Obsolete objections.** The August assessment ([`response-to-rip-0009.md`](response-to-rip-0009.md),
point 4) noted that the non-punitive mempool classification was not yet in the reference
implementation. It is present in
`v1.1.0-rc1` (commit `9426ca366`); that objection no longer applies.

## 3. What Community Core adopts from the RIN3 implementation

Three practices are applied to the signature rule in the same spirit as in the RIN3 implementation:
rejecting non-conforming transactions at mempool admission and not only in block validation,
classifying that rejection as a recent consensus change so honest peers are not penalized, and
switching the wallet to the new regime as soon as the *next* block is the activation block. No code
is copied; the practices are standard fork engineering and are credited here for accuracy.

## 4. Other rule differences between the two implementations

Verified in the source of `Rin-coin/rincoin` at commit `a1b12dc8c` and of the Rincoin Community Core
1.2.0 development build (2026-09-20; its base is `rincoin-community/rincoin-core` `dev` at commit
`7373f1e0f`):

| Rule | Community Core 1.2.0 (development build) | Rin-coin/rincoin v1.1.0-rc1 | Unchanged v1.0.x |
|---|---|---|---|
| Subsidy, heights 840,000 – 234,587,499 | 4 / 2 / 1 / 0.6 RIN (S6/b) | identical values and boundaries | 3.125 RIN, halving every 210,000 |
| Subsidy from 234,587,500 | 0 | 0.6 RIN, no terminal cutoff in consensus (a 168,000,000 RIN cap exists as an accounting constant that no consensus rule reads) | 0 (right shift exhausts at height 13,440,000) |
| Block 840,000 coinbase | must claim exactly 4 RIN plus fees | ordinary upper bound only (a lower claim is accepted) | ordinary upper bound only |
| Transaction replay protection | `SIGHASH_FORKID` signature hash, fork ID 840 | required `nVersion = 0x52494e33` | none |
| Standard transaction versions | 1, 2 | 1, 2, `0x52494e33` | 1, 2 |
| Taproot / MWEB (mainnet) | Litecoin-inherited heights 2,161,152 / 2,217,600 | both set to never activate | Litecoin-inherited heights |
| Version-bits window | 8,064 blocks (threshold 6,048) | 7,920 blocks (threshold 5,940) | 8,064 |
| Service bits | no new bit | `NODE_RIN3` (bit 25), required for outbound peers | none |
| Protocol version | 70019; minimum peer version 70018 from 840,000 | 70018; no floor | 70017 |
| `MAX_MONEY` | 168,000,000 RIN | 168,000,000 RIN | 168,000,000 RIN |
| Test networks | testnet interval 2,100 (transition at 8,400); regtest and preview interval 210 (transition at 840); 60 s spacing | testnet and regtest interval 210, fork at height 840, regtest spacing 3,000 s | testnet interval 210,000; regtest interval 150 |

Practical consequences at height 840,000, given these rules:

- An empty block 840,000 claiming exactly 4 RIN + fees can be valid for both new
  implementations and is invalid for unchanged software.
- The first block containing an ordinary transaction is valid for at most one of the two new
  implementations: a RIN3-version transaction carries a historical-style signature, which Community
  Core rejects at 840,000 and above; a Community Core transaction carries version 1 or 2, which
  Rin-coin/rincoin rejects.
- On regtest the two new implementations share the genesis block, the message start, the halving
  interval (210) and the transition height (840); they differ in when MWEB activates (by height in
  Community Core, by time in Rin-coin/rincoin), which the regtest-only `-vbparams` option aligns at
  run time. Cross-implementation tests can therefore run on regtest with unmodified binaries of
  both. The unchanged v1.0.x software needs its regtest halving interval changed from 150 to 210 to
  take part. Their testnets are not rule-compatible with each other.
- The Taproot/MWEB schedules and the terminal cutoff differ only at heights far beyond 840,000;
  they are listed so that a future alignment covers them, not because they matter for the
  activation.

## 5. Observed behavior

On 2026-09-21 the three implementations were run side by side on a private regtest chain: the
Community Core 1.2.0 development build, the unmodified official `v1.1.0-rc1` release binary of
Rin-coin/rincoin, and v1.0.5 built from source with the one-line regtest change named above. Blocks
were mined by each implementation's own miner and handed to the others with `submitblock`;
transactions were made by each implementation's own wallet. Method, identities, hashes and the full
result tables are in
[`../verification/core-1.2.0-dev.2/`](../verification/core-1.2.0-dev.2/cross-implementation.md).
The heights below are regtest heights; 840 stands for 840,000.

- **Empty blocks.** An empty block at height 840 claiming 4 RIN is accepted by both new
  implementations whichever of them mined it, and rejected by v1.0.5 (`bad-cb-amount`). The two stay
  on one chain for as long as blocks are empty.
- **A block 840 of the unchanged software** (3.125 RIN) is rejected by Community Core
  (`bad-cb-amount-transition`) and accepted by Rin-coin/rincoin, which then builds its own 4 RIN
  block on top of it. Community Core rejects that block and every later one for their ancestor,
  whatever work accumulates on them.
- **The first ordinary transaction separates the two new implementations.** A block with a Community
  Core transaction is rejected by Rin-coin/rincoin (`bad-tx-rinhash-version`); a block with a
  Rin-coin/rincoin transaction is rejected by Community Core (`Signature must use SIGHASH_FORKID`).
  Both mempools refuse the other's transactions as a recent consensus change
  (`bad-tx-rinhash-version`, `old-style-sig-fork-id`).
- **Toward the unchanged rules the two mechanisms differ as described in §2.** A Community Core
  transaction is invalid for v1.0.5 in a block (the signature does not verify there). A Rin-coin/rincoin
  transaction is refused by the v1.0.5 mempool (`version`, a standardness rule) but is accepted
  by v1.0.5 when a block contains it. In the other direction both new implementations reject
  v1.0.5 transactions in blocks at and above the transition height.
- **The signature rule is not a checkpoint.** Community Core reorganizes onto a longer branch of
  empty Rin-coin/rincoin blocks; its own confirmed transaction returns to its mempool and is
  confirmed again in its next block, which Rin-coin/rincoin then rejects.
- **Peers.** Manual connections between all three hold below the transition height. Above it,
  Community Core and v1.0.5 (protocol version 70017) no longer connect to each other, in either
  direction; connections with Rin-coin/rincoin hold. (Its automatic outbound peer selection asks
  for service bit 25, which only its own nodes set; that was read in its source, not tested.)

## 6. Bottom line

Community Core 1.2.0 does not adopt RIN3 because a required transaction version separates
transactions from the unchanged rules only by policy, not by consensus, and because it permanently
repurposes a field with ordinary uses. It uses the replay-protected signature hash of Bitcoin Cash
and Bitcoin Gold with a fork ID of its own, which is invalid in both directions at the consensus
level, at the cost of requiring every signer to produce it. The
mempool and block-assembly practices of the RIN3 implementation are sound and are applied to the
signature-hash design as well. Community Forge will contact the maintainers of every known
implementation to align the rules at 840,000; nothing in this document assumes such an agreement.
