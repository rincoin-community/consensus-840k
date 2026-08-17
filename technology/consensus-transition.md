# Rincoin Height-840,000 Consensus Transition — Technical Overview

Status: Discussion draft (Revision 4.0 — supersedes the two-scenario Revision 3.2 working text)

Date: 2026-08-16

This document explains the *mechanism* Rincoin Core will use if the height-840,000 monetary
decision produces more than one continuation, and the small set of design choices that mechanism
depends on. It is not a claim that a split is decided or wanted. The monetary decision itself —
which of S1, S5/b, or S6/b (or no change) the network adopts — is covered in
[`../analysis/`](../analysis/) and summarized in the [root README](../README.md); this document
only covers the technical questions that follow once someone might disagree.

**First preference: one common consensus, one chain.** Everything below exists so that *if*
agreement fails, the disagreement is deterministic and testable instead of ambiguous.

## 1. The problem in one paragraph

Every Rincoin implementation shares identical history below height 840,000. A consensus change at
that height can produce two continuations that still share genesis, blocks, UTXOs, addresses, and
ordinary network conventions. The engineering task is not "encode a new subsidy" — it is making
sure a node following one continuation cannot accidentally validate a block from the other as part
of its active chain. Transaction replay (a valid transaction confirming on *both* continuations) is
a related but separate problem, covered in
[§6](#6-transaction-replay-a-sighash-level-fork-identifier).

## 2. Why a subsidy difference alone does not separate two chains

Rincoin's coinbase rule is an upper bound, not an exact amount: a block is invalid only if its
coinbase claims *more* than the permitted subsidy plus fees. A miner may claim less, including
zero. So a block built under a larger-subsidy rule can still satisfy a smaller-subsidy rule simply
by underclaiming — two implementations with different maximum subsidies can end up accepting the
same block. Comparing headline subsidy numbers does not prove the two rule sets produce disjoint
block sets.

This is why the selected branch needs an independent, explicit, scheduled identifier, regardless of
which subsidy schedule it uses. We are not adding a mandatory minimum or exact-claim rule to fix
this — that would itself be a consensus change affecting fees, pools, and historical behavior. We
add a marker instead.

## 3. The three monetary candidates under review

The full comparison (twelve schedules, S0–S7, scored against five criteria) lives in
[`Rincoin_Monetary_Scenario_Analysis`](../analysis/Rincoin_Monetary_Scenario_Analysis.qmd); the
short version is [`Rincoin_Monetary_Review_Summary`](../analysis/Rincoin_Monetary_Review_Summary.qmd).
Three bounded schedules reached the principal public-review set:

| | Subsidy at 840,000 | Activation shock | Later schedule | Maximum issuance | Rule shape |
|---|---|---|---|---|---|
| **S0** (unchanged) | 3.125 RIN | — | halves every 210,000 blocks forever | ≈21M RIN | one rule, no change |
| **S1** | 5.9375 RIN | ≈5% | ×19/20 every 210,000 blocks, no floor | ≈44.625M RIN | one formula |
| **S5/b** | 6.25 RIN (unchanged) | none at activation | halves every 2,100,000 blocks (~4y), first cut at height 2,730,000 | ≈44.625M RIN | one formula, longer epoch |
| **S6/b** | 4 RIN | ≈36% | steps to 2 → 1 → 0.6 RIN, flat 0.6 RIN through height 234,587,499, then zero | exactly 168,000,000 RIN | four phases + fixed terminal cutoff |

None of these is adopted. S1 and S5/b currently score highest on the analysis's monetary criteria
and spend almost the same total issuance on different timing; S6/b is carried forward as the
bounded, terminating version of the publicly circulated "Customized Halving" direction, even though
its own score is lower (a multi-century flat 0.6 RIN phase before it stops).

**Exactly one candidate will be compiled into the final release — never a runtime choice.** See
[§7](#7-release-safety-no-accidental-activation).

Two schedules were *excluded* from this candidate set on a fixed policy gate (bounded issuance),
not on their score: **S3** (a perpetual 0.5 RIN tail) and **S7**, the unbounded implementation of the
same 4 → 2 → 1 → 0.6 RIN path as S6/b but without S6/b's terminal cutoff. S7 corresponds to the
schedule published as Aevust's RIP-0002; our assessment of that proposal, and of the related
RIP-0009, is in [`response-to-rip-0009.md`](response-to-rip-0009.md).

## 4. Branch identity: what does not work, and what does

A P2P protocol version, a service-bit flag, and a user-agent string are all useful for capability
negotiation, but none of them proves which blocks a peer actually validates — they are
self-reported, unauthenticated, and a node on the wrong branch can advertise any of them. Raising a
number does not make a chain preferred or valid. So none of these fields carries branch identity in
this design; they remain what they already are (transport/capability hints), and separately:

- **`branch_id`** — an opaque, randomly generated 128-bit value identifying one long-lived
  development/consensus lineage. A later scheduled fork of the *same* lineage keeps the same
  `branch_id` and increments `fork_no`. It is not authentication (a copier can reuse a published
  value); it is a collision-avoidance identifier, and 128 random bits make accidental collision
  negligible.
- **`fork_no`** — increments once per scheduled activation height within a lineage.
- **`scenario_id`** — selects the specific rule (S1, S5/b, or S6/b) active within that fork. Left
  unassigned in this draft; assigned to whichever candidate the public review selects.

## 5. The decisive mechanism: a scheduled coinbase commitment

From height 840,000 (H1), the selected branch requires exactly one zero-valued coinbase output: an
`OP_RETURN` followed by a direct 28-byte push, distinct from and additional to the witness
commitment.

| Offset | Size | Field | Value |
|---:|---:|---|---|
| 0 | 4 | `magic` | ASCII `RINF` (`52 49 4e 46`) |
| 4 | 1 | `format_version` | `01` |
| 5 | 16 | `branch_id` | opaque, published lineage ID |
| 21 | 4 | `fork_no` | uint32 big-endian |
| 25 | 2 | `scenario_id` | uint16 big-endian |
| 27 | 1 | `flags` | `00` |

Full script: `6a1c` + 28-byte payload, 30 bytes total, `CTxOut` value exactly zero, any output index.

**Validation:** scan every coinbase output for the `RINF` namespace before deciding. Zero matches
fails as missing. More than one match fails as a duplicate — a correct record does not hide a wrong
one. Exactly one candidate passes only if every byte (script, value, branch, fork, scenario, format,
flags) matches exactly; truncated, extended, non-minimal-push, or unknown-format records all fail.
The test-vector corpus uses synthetic branch ID `00112233445566778899aabbccddeeff`, which is never a
mainnet value.

**What this guarantees:** at H1, contextual full-block validation rejects the first block with a
missing or wrong commitment, so it cannot connect to the active chain — regardless of how much
proof-of-work an incompatible continuation accumulates on top of it.

**What this does not guarantee:** headers from another continuation can still pass proof-of-work
and header checks, be stored, and even appear as `bestheader`; this design does not reject them
before download. It does not eliminate wasted bandwidth, guarantee a decisive block isn't withheld
by a hostile peer, or replace transaction replay protection (see
[§6](#6-transaction-replay-a-sighash-level-fork-identifier)). Operators must watch the validated
active tip, not `bestheader` — see the [contingency options](#51-if-commitment-only-turns-out-to-be-operationally-insufficient)
below for what improves this.

**Mining templates:** `getblocktemplate` supplies the exact script, zero value, branch, fork, and
scenario as consistent fields. A pool rebuilding a coinbase adds exactly one such output, updates
the output count, and keeps the witness commitment, BIP34 height, payout, and extranonce behavior
unchanged.

### 5.1 If commitment-only turns out to be operationally insufficient

A second, currently **inactive** layer is designed and tested but not selected: reserving header
`nVersion` bit 30 so an ordinary bit-clear incompatible header fails *before* its block is
downloaded, improving IBD and reducing wasted traffic if a persistent incompatible continuation with
real hashrate turns out to exist. It does not authenticate anything either — if another continuation
also sets bit 30, headers pass both sides and the coinbase commitment above stays decisive.

**We might activate this** if, before the tuple is frozen, there is evidence of significant
incompatible hashrate/node support, unreliable peer discovery, or someone deliberately copying our
commitment tuple. **We will not activate it** by default, and the decision — yes or no — is due
**31 August 2026**, before any signalling release ships. Enabling it later requires a new tuple,
fresh publication, and repeated tests.

## 6. Transaction replay: a sighash-level fork identifier

This is a separate mechanism from §5, solving a separate problem: the coinbase commitment decides
which *block* belongs to which branch and works even for a block with no ordinary transactions in
it; nothing about it constrains individual transactions. Block separation does **not** protect
against transaction replay: a transaction valid against
shared pre-H1 history can confirm on both continuations unless signatures are made chain-specific.

**Chosen direction: a sighash-level fork identifier, not a transaction-version marker.** From H1,
every non-coinbase input's signature must be computed with a `sig_fork_id` value mixed into the
sighash preimage, rather than requiring a fixed value in `nVersion` the way RIN3 does. `sig_fork_id`
is derived deterministically from the identifiers already defined in [§4](#4-branch-identity-what-does-not-work-and-what-does)
— `sig_fork_id = SHA256(branch_id || fork_no || scenario_id)[:8]` — so it needs no separate
coordination or reservation process. The requirement is height-gated by the confirming block, not
carried in any transaction field: nothing about the transaction format itself signals branch
identity, and `nVersion` stays free for legitimate future use. It is mandatory and unconditional —
no opt-in, no legacy path left available post-H1. This corrects a mistake we made ourselves before
settling on this design: an earlier internal draft explored requiring a fixed `nVersion` value, the
same idea RIN3 later published independently, and we dropped it once we judged that permanently
repurposing a shared transaction field was the wrong tool for the job. See
[`response-to-rip-0009.md`](response-to-rip-0009.md) for the full technical comparison.

Both replay directions need an explicit rule — this is not automatic in one direction:

- A transaction signed under our rule fails signature verification on an old or unrelated
  continuation automatically, because that validator computes a different digest for the same bytes.
  No cooperation from the other side is required.
- A transaction signed the old way and submitted to *our* chain post-H1 is **not** automatically
  rejected by math alone; it needs the same kind of explicit consensus rule RIN3 needed, just applied
  to the sighash construction instead of to `nVersion`.

**Scope for H1: legacy pre-SegWit and SegWit v0 (BIP143) sighash only.** SegWit has been active on
Rincoin mainnet since height 26,500, so both spending types can appear in any block around 840,000
and both need coverage from day one.

**Explicitly deferred, not forgotten: Taproot and MWEB.** Neither has activated on mainnet yet —
Taproot's deployment starts at height 2,161,152 and MWEB's at 2,217,600, both well past 840,000 — so
no Taproot-spend or MWEB-kernel transaction can exist in any block before then regardless of what we
do here. The commitment is to extend `sig_fork_id` coverage to both before their own activation
heights arrive, as their own separately scheduled follow-up work, not to leave them unprotected
indefinitely. See [`replay-protection-plan.md`](replay-protection-plan.md) for the phased approach
and the H1 scope cut.

We also keep two pieces of RIN3's engineering, applied to this design instead of a version marker:
mempool/block-assembly rejection so a wrongly-signed transaction can't stall block production, and a
non-punitive rejection classification for honest peers relaying pre-H1 residue.

**We will not** bundle this into the monetary-scenario decision itself — see
[`response-to-rip-0009.md`](response-to-rip-0009.md) for why that coupling is a design mistake we're
avoiding. If the design, implementation, tests, and genuine ecosystem adoption time can't all be
completed before H1, we ship with the operational runbook instead of rushing consensus code — see
[`replay-protection-plan.md`](replay-protection-plan.md).

## 7. Release safety: no accidental activation

Two separate release profiles exist so a signalling build can never accidentally mine the new rules:

- **Signalling release (P-SIGNAL):** validates S0 forever, has no runtime path to enforce the new
  rules, and may only *emit* the frozen proposal commitment before H1 as a marker. From 720 blocks
  before H1 it shows a persistent warning; at H1 it stops emitting the marker and refuses
  `getblocktemplate`/mining with an explicit expiry error, while continuing ordinary S0 validation
  and non-mining RPC.
- **Final release (F-FINAL):** compiles exactly one immutable scenario and schedule, with **no
  runtime scenario or activation selector**. Changing branch ID, format, fork/scenario, flags, or
  activation height requires a fresh publication and test cycle — it is never a config flag.

Competing final mainnet scenarios are never distributed as operator-selectable binaries.

## 8. A future second fork (H2)

The schedule is an ordered history, not a single replaceable value. A future H2 entry keeps the same
`branch_id`, increments `fork_no`, and selects its own `scenario_id`. A new node validates fork-1
rules through `[H1, H2)` and fork-2 rules from H2 on; an old fork-1-only node keeps expecting the
fork-1 commitment and correctly rejects the first fork-2 block. Every historical entry stays
available for full IBD and reindexing indefinitely.

## 9. What we will not do

- Treat any header bit, protocol version, service flag, or user-agent string as branch
  authentication or an ownership claim.
- Ship a production binary with a runtime-selectable monetary scenario.
- Adopt an unbounded/perpetual-tail schedule (S3 or S7) as the Rincoin Core default — see
  [§3](#3-the-three-monetary-candidates-under-review).
- Add a mandatory minimum/exact coinbase claim to "fix" the underclaim issue in §2 — it's a bigger,
  unrelated consensus change with its own review burden.
- Bundle unrelated consensus changes (e.g., a replay-protection marker) into one non-negotiable
  package with the monetary decision.
- Claim a release is "ready" without executed, reviewable test evidence (vectors, acceptance
  matrices, IBD/reorg tests) attached to the exact frozen tuple.

## 10. Reviewing this design

Consensus-critical claims here should be checked against the (forthcoming, published alongside the
selected scenario) commitment test-vector corpus and acceptance matrix, and against the relevant
[`Rincoin_840k_*_Consensus_Change_Specification`](../analysis/) for whichever candidate is under
discussion. Report arithmetic or implementation defects with the affected height, expected vs.
actual result, and reproduction steps. Participating in review does not imply support for
activation.
