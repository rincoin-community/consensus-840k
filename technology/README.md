# Rincoin Consensus Transition — Technology

Status: Discussion draft — first publication

This folder covers the *technical* side of the height-840,000 decision: how Rincoin Core keeps two
possible continuations from silently mixing, if the community doesn't converge on one chain. It does
not decide monetary policy — that comparison lives in [`../analysis/`](../analysis/) and is
summarized in the [root README](../README.md). Nothing here is adopted, final, or active.

**First preference: one common consensus, one chain.** Everything below is a contingency for the
case where agreement isn't reached in time, kept deterministic and testable rather than ambiguous.

## In brief, for pool, exchange, wallet, and mining-software developers

If you maintain infrastructure or client software and just need to know whether this affects you
before reading further, two separate mechanisms are planned, and one thing is explicitly off the
table:

- **Blocks** are told apart by one exact, zero-value coinbase output carrying `branch_id` /
  `fork_no` / `scenario_id`. If you run a pool, or you write **solo/GBT-based miner software that
  builds its own coinbase transaction**, you'll need to add this output — once a scenario and the
  exact identifier values are frozen, `getblocktemplate` will supply it as ready-made fields
  ([§5](consensus-transition.md#5-the-decisive-mechanism-a-scheduled-coinbase-commitment)) rather
  than requiring you to hand-build it.
- **Stratum-only miner clients** that just do proof-of-work and submit shares to a pool don't build
  a coinbase themselves, so this doesn't touch your code directly — but don't treat protocol
  version, user-agent strings, or service-bit flags as branch identity if you ever add
  branch-aware routing; none of them are
  ([§4](consensus-transition.md#4-branch-identity-what-does-not-work-and-what-does)). Also expect an
  explicit, documented mining-refusal error from any pre-final signalling release once height
  840,000 is reached
  ([§7](consensus-transition.md#7-release-safety-no-accidental-activation)) — that's expected
  behavior, not a bug to work around.
- **Transactions** are told apart, separately, by mixing a fork identifier (`sig_fork_id`) into the
  signature hash of every non-coinbase input from height 840,000. If you run wallet or signing
  infrastructure, you'll need to compute signatures this way from that height. This does not apply
  to mining software, which doesn't construct ordinary signed spends.
- **We are not changing the transaction `nVersion` field for this.** No version-string requirement
  to implement — that's the "RIN3" approach circulating elsewhere, and we're deliberately not using
  it.
- Nothing here is final yet: which monetary scenario, the exact identifier values, and the
  activation tuple are all still open for review. Read on for what's decided, what's conditional,
  and what we explicitly won't do.

## Read this first

- **[`consensus-transition.md`](consensus-transition.md)** — the technical design: why a subsidy
  difference alone can't separate two chains, the scheduled coinbase commitment that does, the three
  monetary candidates it needs to support (S1, S5/b, S6/b), and the release safeguards that prevent
  accidental activation.
- **[`response-to-rip-0009.md`](response-to-rip-0009.md)** — our assessment of the two external
  proposals published by Aevust (RIP-0002 "Customized Halving" and RIP-0009 "RIN3"), which we do not
  adopt as specified, with the specific technical reasons and the parts we do think are good ideas.
- **[`replay-protection-plan.md`](replay-protection-plan.md)** — the phased plan for our own
  transaction-replay-protection design (a sighash-level fork identifier, not a version-field marker),
  scoped to what can genuinely be ready by height 840,000.

## What we will do

- Invite direct technical coordination with other implementations first, before publishing or
  signalling any separation mechanism.
- If that fails: ship one exact, byte-tested marker (a scheduled coinbase commitment carrying
  `branch_id` / `fork_no` / `scenario_id`) so a node can't accidentally validate a block from an
  incompatible continuation.
- Select **exactly one** bounded monetary scenario — from S1, S5/b, S6/b, or no change (S0) — through
  open public review, and compile only that one into the final release.
- Ship a signalling-only release that can never mine the new rules by accident, separate from the
  final release that has no runtime scenario switch at all.
- Publish test vectors and an acceptance matrix for the frozen tuple before any final release.
- Pursue transaction replay protection as a **sighash-level fork identifier** (`sig_fork_id` mixed
  into the signature hash, derived from `branch_id`/`fork_no`/`scenario_id`) rather than a
  transaction-version marker, scoped for H1 to legacy and SegWit v0 spends — the only types that can
  exist in any block by height 840,000. See
  [`replay-protection-plan.md`](replay-protection-plan.md).
- Extend that same fork-identifier coverage to Taproot and MWEB before *their* activation heights
  (2,161,152 and 2,217,600 — both well after 840,000, so there's no exposure to close at H1, only a
  commitment not to forget them).

## What we might do (and under what conditions)

- **Header-level early filtering** (an `nVersion` bit that lets an incompatible header fail before
  its block downloads) — only if, before the tuple is frozen, there's evidence commitment-only
  separation is operationally inadequate (persistent incompatible hashrate, unreliable peer
  discovery, deliberate tuple copying). Decision due **31 August 2026**; default is *no*.
- **A dedicated P2P branch-declaration message** for routing efficiency, once its wire format has
  independent test vectors — an optimization, never a validity check.
- **Fall back to an operational runbook only** (service freezes, isolated wallets, coin splitting)
  for transaction replay at H1, if the sighash fork-identifier design can't genuinely be specified,
  implemented, tested, *and* given real ecosystem adoption time before height 840,000.

## What we won't do

- Treat a header bit, protocol version, service flag, or user-agent string as authentication or an
  ownership claim over a chain.
- Ship a production binary where the monetary scenario is a runtime flag.
- Adopt an unbounded/perpetual-tail schedule (S3, or S7 — unbounded "Customized Halving"
  implementation) as the Rincoin Core default; it fails our own bounded-issuance requirement.
- Add a mandatory minimum/exact coinbase claim just to work around the underclaim argument in
  [`consensus-transition.md §2`](consensus-transition.md#2-why-a-subsidy-difference-alone-does-not-separate-two-chains) —
  that's a bigger, unrelated change with its own review burden.
- Bundle unrelated consensus changes (e.g. a replay-protection marker) into one non-negotiable
  package with the monetary decision — see [`response-to-rip-0009.md`](response-to-rip-0009.md) for
  why we think that coupling is a mistake.
- Reuse the transaction `nVersion` field as a permanent fork-identity marker (RIN3-style) — we tried
  an early version of this idea ourselves and dropped it before RIP-0009 was published, for the same
  reason we're declining it now: it's the wrong tool for the job. See
  [`replay-protection-plan.md`](replay-protection-plan.md) for the alternative.
- Claim a release is "ready" without executed, reviewable evidence attached to the exact frozen
  tuple.

## Comment or object

Corrections, objections, and alternative designs are welcome through the routes in the
[coordination notice](../coordination-notice.md) — GitHub issue/PR/Discussion, the Rincoin Community
Forge Discord, or direct message. Consensus-critical claims should be reported with the affected
height, expected vs. actual behavior, and reproduction steps where possible. Participating in review
does not imply support for activation.
