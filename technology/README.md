# Rincoin Consensus Transition — Technology

Status: Working specification for Rincoin Community Core 1.2.0 (updated 2026-09-20)

This folder covers the *technical* side of the height-840,000 transition as implemented by
Rincoin Community Core: what changes, how blocks and transactions of different continuations are
kept apart, and what integrators must do. The monetary reasoning lives in
[`../analysis/`](../analysis/) and is summarized in the [root README](../README.md).

**Decision status.** Rincoin Community Forge has selected the **S6/b** monetary scenario for its
implementation, because it offers the widest achievable compatibility with other Rincoin software
and the best chance of a common chain. This is a decision about Community Core's own
implementation; it is not a statement that the whole network has agreed. Community Forge will
contact the maintainers of every known Rincoin implementation to align the rules at 840,000. All
rules and constants are fixed as of 2026-09-19; test vectors will be published with the 1.2.0
source.

## In brief, for pool, exchange, wallet, and mining-software developers

- **Subsidy.** From height 840,000 the maximum block subsidy is 4 RIN instead of 3.125 RIN, then
  2 / 1 / 0.6 RIN at 2,100,000 / 4,200,000 / 6,300,000, and 0 from 234,587,500 (168,000,000 RIN
  maximum issuance). Pools and solo miners that take the reward from `getblocktemplate`'s
  `coinbasevalue` need no change.
- **Block 840,000 only** must claim exactly the maximum subsidy plus all fees
  ([`consensus-transition.md §3`](consensus-transition.md#3-the-coinbase-condition-in-block-840000)).
  Claiming the full template value satisfies it; no other height gets a minimum-claim rule. A
  payout scheme that deliberately leaves part of the reward unclaimed would lose that one block.
- **Transactions** are kept apart by a fork identifier (`sig_fork_id`) mixed into the signature
  hash of every legacy and SegWit v0 input from height 840,000. If you run wallet or signing
  infrastructure, you must compute signatures this way from that height
  ([§5](consensus-transition.md#5-transaction-replay-protection-sig_fork_id)). Software that only
  verifies, indexes, relays or mines is not affected. Hardware wallets with fixed Bitcoin firmware
  cannot follow.
- **No coinbase commitment, no required transaction version.** Nothing must be added to the
  coinbase, and the transaction `nVersion` field keeps its ordinary meaning; the "RIN3" required
  version proposed in RIP-0009 and used by another implementation is not part of Community Core
  ([`response-to-rip-0009.md`](response-to-rip-0009.md),
  [`replay-protection-comparison.md`](replay-protection-comparison.md)).
- **Voluntary signalling.** `getblocktemplate` carries a short tag in `coinbaseaux.flags`
  (BIP22). A pool that builds its own coinbase copies the bytes after the BIP34 height push; some
  pool software does this automatically, some ignores the field. It is not a consensus rule and
  not proof of anything ([§6](consensus-transition.md#6-voluntary-signalling-coinbaseauxflags)).
- **Peers.** Protocol version and user-agent strings are diagnostic; 1.2.0 advertises protocol
  version 70019. From 840,000, Community Core disconnects peers announcing a protocol version below
  70018 (a networking policy that predates this change); no service bit is introduced.
- **Timeline.** Mainnet height was about 747,250 on 2026-09-19, roughly 64 days before 840,000. A
  first 1.2.0 development build has been built and tested
  ([`../verification/core-1.2.0-dev.1/`](../verification/core-1.2.0-dev.1/)); its source will be
  published for testing after review, and a stable release is planned by 2026-09-30. These are
  plans, not readiness statements.

## Documents

- **[`consensus-transition.md`](consensus-transition.md)** — the specification: the S6/b rule,
  the block-840,000 condition, why no mandatory branch commitment is used and what that means for
  compatibility, the `sig_fork_id` construction with its exact byte placement and boundary
  behavior, the voluntary signalling tag, node identity, release status and safeguards.
- **[`replay-protection-comparison.md`](replay-protection-comparison.md)** — technical comparison
  of the two replay-protection mechanisms currently planned by Rincoin implementations
  (`sig_fork_id` and the required "RIN3" transaction version), and a table of the other rule
  differences between the implementations as verified in their code.
- **[`response-to-rip-0009.md`](response-to-rip-0009.md)** — our assessment (August 2026, kept
  as published, with a dated status note) of the two external proposals published by Aevust
  (RIP-0002 "Customized Halving" and RIP-0009 "RIN3"), which we do not adopt as specified, with the
  specific technical reasons and the parts we do think are good ideas.
- **[`replay-protection-plan.md`](replay-protection-plan.md)** — implementation status, who must
  change what, and the adoption timeline.

## What we will do

- Ship exactly one compiled-in monetary scenario (S6/b); never a runtime switch.
- Keep `sig_fork_id` as the transaction replay mechanism for legacy and SegWit v0, and extend it
  to Taproot and MWEB before their own activation heights.
- Apply the single block-840,000 coinbase condition and no other minimum-claim rule.
- Publish the final constants, test vectors and executed test evidence with the 1.2.0 source
  before any release is called ready.
- Contact the maintainers of every known Rincoin implementation to align consensus and signature
  rules, with the goal of one chain.

## What we will not do

- Treat a header bit, protocol version, service flag, or user-agent string as branch identity.
- Require a permanent per-block identifier that would by itself prevent a common chain with an
  otherwise rule-compatible implementation.
- Reuse the transaction `nVersion` field as a permanent fork-identity marker (RIN3-style,
  RIP-0009) — we tried an early version of this idea ourselves and dropped it before RIP-0009 was
  published, for the same reason we're declining it now: it's the wrong tool for the job. See
  [`response-to-rip-0009.md`](response-to-rip-0009.md) and
  [`replay-protection-comparison.md`](replay-protection-comparison.md).
- Add an identification `OP_RETURN` to coinbases or ordinary transactions.
- Activate, deactivate, or reschedule Taproot or MWEB as a side effect of this change.
- Ship 1.2.0 without transaction replay protection.

## Comment or object

Corrections, objections, and alternative designs are welcome through the routes in the
[coordination notice](../coordination-notice.md) — GitHub issue, pull request or discussion, the
Rincoin Community Forge Discord, or direct message. Consensus-critical reports should include the
affected height, expected versus actual behavior, and reproduction steps. Participating in review
does not imply support for activation.
