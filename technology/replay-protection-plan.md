# Sighash Fork Identifier — Phased Implementation Plan

Status: Brief, high-level — first draft. Each phase gets its own detailed spec/task list once it
starts; this is a scheduling and scope document, not the specification itself.

Date: 2026-08-16

This is the plan for the transaction-replay-protection design chosen in
[`consensus-transition.md §6`](consensus-transition.md#6-transaction-replay-a-sighash-level-fork-identifier): a fork identifier
mixed into the signature hash, rather than a required transaction-version value. See
[`response-to-rip-0009.md`](response-to-rip-0009.md) for why we're not using the version-marker
approach instead.

## Scope decision: cut hard, cover legacy + SegWit v0 only for H1

SegWit has been active on Rincoin mainnet since height 26,500, so legacy pre-SegWit and SegWit v0
(BIP143) transactions can both appear in any block around height 840,000. Both need `sig_fork_id`
coverage from day one — this is the scope for H1.

Taproot and MWEB are **not** in scope for H1, and don't need to be: checked against
`src/chainparams.cpp`, mainnet Taproot activates at height 2,161,152 and MWEB at 2,217,600 — both
inherited from Litecoin's own historical deployment and both roughly 1.3–1.4 million blocks
(~2.5–2.7 target years) past 840,000. Neither soft fork will have activated by H1, so no
Taproot-spend or MWEB-kernel transaction can exist in a block before then regardless of what we do
now. Cutting them from the H1 critical path removes the largest source of schedule risk (MWEB in
particular is a different cryptographic construction — Pedersen-commitment kernels, not script-based
signatures — and needs its own dedicated review whenever it's tackled). They are tracked as
follow-up work with their own, much longer, runway — not dropped.

## Phases (H1 critical path)

| Phase | Content | Rough duration |
|---|---|---|
| 1. Design & spec | Finalize `sig_fork_id` derivation (`SHA256(branch_id \|\| fork_no \|\| scenario_id)[:8]`); height-gating rule; both-direction enforcement (old-style tx rejected post-H1 by explicit rule; new-style tx fails verification elsewhere automatically); publish as its own reviewable proposal, decoupled from the monetary-scenario decision | ~1 week |
| 2. Legacy + SegWit v0 implementation | Patch sighash preimage construction for both paths; consensus height gate at H1; mempool/block-assembly defense-in-depth and non-punitive peer classification (the two RIP-0009 ideas worth keeping, reapplied here); standardness policy update | ~1–2 weeks |
| 3. Test matrix | Per-input-type vectors (legacy P2PKH/P2SH, P2WPKH/P2WSH, multisig) × pre/post-H1; cross-validation in both replay directions; boundary/off-by-one handling around H1; reorg stress test crossing H1 (adapting RIP-0009's own large-reorg methodology); full IBD regression; fuzzing | ~2–3 weeks, overlapping phase 2's tail |
| 4. Ecosystem adoption window | Publish the final spec early enough for wallets, PSBT tooling, and exchanges to implement and verify independently before enforcement goes live | ~3–4 weeks minimum — least controllable phase; protect its *start date*, not just its duration |
| 5. Signalling & warning tail | Folds into the existing P-SIGNAL / pre-H1 warning pattern already defined for the monetary transition — no separate schedule needed | — |

Phases 1–4, sequenced with realistic overlap, run roughly 7–9 weeks. Against a budget of
~14 weeks to height 840,000 (see open items below), this fits with real margin.

## Follow-up track (not before ~2,161,152 / ~2,217,600)

Extend `sig_fork_id` coverage to Taproot sighash (BIP341) and MWEB kernel signing before each
respectively activates. Independent schedule, independent review (MWEB especially), does not block
H1, and is tracked here specifically so it doesn't get quietly forgotten.

## Fallback

If phases 1–4 can't be genuinely completed — spec, implementation, tests, and real ecosystem
adoption time, not just merged code — before height 840,000, we ship H1 with the operational runbook
instead of rushing consensus code, per
[`consensus-transition.md §9`](consensus-transition.md#9-what-we-will-not-do): don't bundle, and
don't rush.

## Open items before phase 1 starts

- Confirm current mainnet tip height against our own node. This plan assumes roughly 140,000–150,000
  blocks (~14 weeks) remain to height 840,000, based on Aevust's RIP-0002 claiming mainnet
  confirmation "through block ≈690,000" as of early August 2026 — a third-party figure that needs
  independent verification, not a number we've confirmed ourselves.
- Confirm engineering resourcing: this now runs in parallel with the header-isolation contingency
  decision (due 31 August 2026) and the monetary-scenario selection itself.
