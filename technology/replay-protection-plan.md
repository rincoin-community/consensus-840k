# Sighash Fork Identifier — Implementation and Adoption Plan

Status: Plan and status document, updated 2026-09-20 (first draft 2026-08-16)

This is the schedule and scope document for the transaction-replay-protection design specified in
[`consensus-transition.md §5`](consensus-transition.md#5-transaction-replay-protection-sig_fork_id):
a fork identifier (`sig_fork_id`) mixed into the signature hash, rather than a required
transaction-version value. See [`response-to-rip-0009.md`](response-to-rip-0009.md) and
[`replay-protection-comparison.md`](replay-protection-comparison.md) for why we're not using the
version-marker approach (RIP-0009) instead.

## Scope: legacy and SegWit v0 only for height 840,000

SegWit has been active on Rincoin mainnet since height 26,500, so legacy pre-SegWit and SegWit v0
(BIP143) transactions can both appear in any block around height 840,000. Both are covered from
the activation block.

Taproot and MWEB are not in scope and do not need to be: on mainnet, Taproot's deployment starts
at height 2,161,152 and MWEB's at 2,217,600 (both inherited from Litecoin's schedule, both roughly
1.3–1.4 million blocks after 840,000). No Taproot spend or MWEB kernel can exist in a block before
then, whatever is done now. They are tracked as follow-up work with their own review (MWEB in
particular is a different cryptographic construction and needs a dedicated design), not dropped.

## Status of the work

| Phase | Content | Status on 2026-09-20 |
|---|---|---|
| 1. Design and specification | derivation, byte placement, height gating, both-direction enforcement, `SIGHASH_SINGLE` edge case | specified in `consensus-transition.md §5`; constants and the `SIGHASH_SINGLE` rule fixed 2026-09-19 |
| 2. Legacy + SegWit v0 implementation | preimage construction for both paths; consensus height gate; mempool admission and boundary eviction; non-punitive rejection classification (the two RIP-0009 ideas worth keeping, reapplied here); wallet, raw-transaction, PSBT and `rincoin-tx` signing; validation-cache keying | implemented in the 1.2.0 development build (`v1.2.0-dev.1`), including the `SIGHASH_SINGLE` rule, boundary eviction in both directions, and the checking of signatures made by other parties (multi-party raw transactions, `combinerawtransaction`, `finalizepsbt`, `analyzepsbt`, the GUI); an earlier form was in the testing-mode branch `consensus/s6b-testing` (Aug 23 – Sep 5, 2026). The source of the development build has not been published yet |
| 3. Test matrix | per-input-type vectors (P2PKH, P2SH, P2WPKH, P2WSH, multisig) × pre/post-840,000; both replay directions; boundary and off-by-one cases; reorganization across the boundary (adapting RIP-0009's own large-reorg methodology); cross-implementation cases; full regression suite | executed for the development build: unit vectors generated independently of the C++ code; functional tests for every listed input type and hash type on both sides, in the mempool and in blocks, at the boundary and across reorganizations; wallet, raw-transaction and PSBT flows; a three-implementation regtest matrix. Results: [`../verification/core-1.2.0-dev.1/`](../verification/core-1.2.0-dev.1/). Not yet covered: see the open items there |
| 4. Ecosystem adoption window | final constants and vectors published early enough for wallets, PSBT tooling, exchanges and pools to implement and verify independently | starts with the publication of the 1.2.0 development build; a stable release is planned by 2026-09-30 |
| 5. Signalling | voluntary `coinbaseaux.flags` tag, no consensus effect | part of 1.2.0 |

There is no plan to ship 1.2.0 without transaction replay protection. If the implementation or
its verification cannot be completed in time, the question is the release schedule, not the
removal of the rule.

## Who must change what

| Component | Required change |
|---|---|
| Rincoin Community Core (node, wallet, RPC, PSBT, `rincoin-tx`) | in 1.2.0 |
| Electrum-style wallets (Electrin) | implement the new preimage in the legacy and BIP143 signing paths; decide the regime from the verified chain height, with an explicit override for offline signing; refuse to sign near the boundary rather than guess; hardware-wallet plugins cannot follow and must be disabled for the new regime |
| Exchange, pool-payout and custody systems signing outside Core | same as above; systems that sign through the Core wallet RPCs need no change beyond upgrading the node |
| PSBT tooling and cosigners | agree on the regime out of band; PSBT carries no height |
| Hardware wallets | unusable for the new regime unless the vendor adds support |
| Fulcrum/Electrum servers, explorers, block relays | no signature change; upgrade the backing node before 840,000 |
| Pools (yiimp, Miningcore, others), solo GBT miners, stratum miners, proxies | no signature change; the ordinary node upgrade, the voluntary `coinbaseaux.flags` tag, and one thing to check: the coinbase of block 840,000 has to claim the full `coinbasevalue` of the template (payout schemes that leave part of the reward unclaimed would lose that block) |

## Timeline

On 2026-09-19 the mainnet height was about 747,250, roughly 92,750 blocks (about 64 days at the
60-second target) before 840,000. The stable release planned by 2026-09-30 leaves about seven
weeks for ecosystem adoption. Exchanges and services should plan a deposit and withdrawal pause
around the activation and confirm which continuation their node, wallet and backend follow
before resuming; a one-day window is a plan, not a consensus guarantee.

## Follow-up track (before heights 2,161,152 and 2,217,600)

Extend `sig_fork_id` coverage to the Taproot signature hash (BIP341) and to MWEB kernel signing
before each activates. Independent schedule, independent review, no effect on 840,000.
