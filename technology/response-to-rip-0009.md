# Response to RIP-0009 ("RIN3") and RIP-0002 ("Customized Halving")

Status: Community technical response — not a consensus document

Date: 2026-08-16

Subject documents: [RIP-0009](https://github.com/Aevust/rincoin-rips/blob/main/rip-0009/rip-0009.md)
("RinHash Transaction Version Enforcement / RIN3") and
[RIP-0002](https://github.com/Aevust/rincoin-rips/blob/main/rip-0002/rip-0002.md) ("Customized
Halving Schedule"), both authored by Aevust and published at
[github.com/Aevust/rincoin-rips](https://github.com/Aevust/rincoin-rips).

## Why we're answering this in public

Aevust has published RIPs that activate, at our own decision height of 840,000, both a specific
unbounded monetary schedule (RIP-0002) and a mandatory transaction-marker rule bundled to it
(RIP-0009). RIP-0002's schedule is exactly the one we model and *exclude* as **S7** in
[our monetary analysis](../analysis/Rincoin_Monetary_Scenario_Analysis.qmd). Because both documents
reference the same activation height and are circulating publicly, we think the community deserves
an explicit, technical answer — not silence, and not a dismissal without reasons.

We evaluate both fairly on their engineering merits. We do not adopt either as published.

## What's being proposed, briefly

**RIP-0002** defines a seven-phase-plus-terminal subsidy schedule: 4 RIN from height 840,000, 2 RIN
from 2,100,000, 1 RIN from 4,200,000, then 0.6 RIN "perpetually" from 6,300,000 — the same path as
our **S6/b**, but without S6/b's finite terminal cutoff at height 234,587,500. RIP-0002's own text
says the 168,000,000 RIN cap is "reached" at that height, after which the 0.6 RIN reward
"transitions from new issuance to reincarnated dormant assets per RIP-0005."

**RIP-0009** requires every non-exempt transaction from height 840,000 onward to carry
`nVersion = 0x52494e33` ("RIN3"), enforced at the consensus, mempool, and block-assembly layers, as
replay protection against pre-fork and sibling chains. It is defined to activate at
`4 × nSubsidyHalvingInterval`, i.e. bundled to RIP-0002's activation height by construction.

## Where we agree

- **Replay protection is a real, currently open problem.** We say so ourselves — see
  [`consensus-transition.md §6`](consensus-transition.md#6-transaction-replay-a-sighash-level-fork-identifier). RIP-0009 is
  right to take it seriously instead of leaving it implicit.
- **The mempool/block-assembly defense-in-depth design is sound.** Rejecting a legacy-version
  transaction at both mempool admission and block assembly, not just at consensus validation, closes
  a real stall-the-miner DoS vector that a consensus-only check would leave open.
- **Capability signaling over protocol-version floors is the right instinct.** Using a dedicated
  service bit (`NODE_RIN3`) with preferential outbound peering, instead of raising
  `MIN_PEER_PROTO_VERSION` and disconnecting older peers, matches a principle we hold ourselves:
  protocol version is not branch identity, and a version floor risks partitioning honest lagging
  peers along with hostile ones. RIP-0009 gets this right and explains why clearly.
- **Non-punitive rejection classification for lagging honest peers** (`TX_RECENT_CONSENSUS_CHANGE`
  instead of the instant-discouragement `TX_CONSENSUS` bucket) is a legitimate, well-precedented
  technique for exactly the failure mode it targets.
- **One well-announced fork event beats staggered surprise changes**, all else equal.

## Where we differ, and why

**1. RIP-0002 fails our bounded-issuance requirement, despite presenting itself as capped.**
"Reached" at height 234,587,500 only holds if the following sentence — the 0.6 RIN reward
"transitions... to reincarnated dormant assets per RIP-0005" — is a real, specified, ratified
consensus rule. It isn't one today: there is no consensus-safe method shown anywhere to prove
permanent abandonment versus long-term dormancy, no adversarial threat model, and no deployed code.
Our own analysis reached the same conclusion independently, in its
[Proof of Rinne scope note](../analysis/Rincoin_Monetary_Scenario_Analysis.qmd): the broader
recirculation idea is a legitimate long-horizon research question, but it is not a specified
Layer-1 rule today. Until RIP-0005 is real, RIP-0002's 0.6 RIN phase is unbounded tail emission —
which is precisely our **S7**, excluded from the bounded candidate set on that basis alone, not on
its score.

We'd also gently push back on RIP-0002's framing that the schedule is already "deployed... embedded
at genesis." Every scenario in our review, S0 through S7, shares identical pre-840,000 history,
because none of them changes anything before that height. Sharing history with the live chain isn't
evidence that a specific post-840,000 schedule was chosen.

**2. RIP-0009 hard-couples a replay-protection mechanism to one specific, contested monetary
schedule.** `nRinHashForkHeight` is asserted equal to `4 × nSubsidyHalvingInterval` — RIP-0002/S7's
activation height — in every chain-params constructor. But *which* monetary scenario activates at
840,000 (S1, S5/b, S6/b, or nothing) is the exact open question this whole public review exists to
answer. Replay protection should be decidable on its own technical merits, independent of which
monetary rule wins, not shipped as a rider on one proposal that our own eligibility gate already
disqualifies.

**3. RIN3 permanently repurposes every ordinary transaction's `nVersion` field, forever, for one
narrow job.** Our own branch-separation design (see
[`consensus-transition.md §5`](consensus-transition.md#5-the-decisive-mechanism-a-scheduled-coinbase-commitment))
deliberately does the opposite: one exact, additional, zero-value coinbase output, once per block,
leaving ordinary transactions untouched. RIN3 instead pins a magic constant into the version field of
every non-coinbase transaction indefinitely after H1. That forecloses any future legitimate use of
transaction `nVersion`, and it widens the compatibility surface considerably: every wallet, indexer,
hardware signer, and PSBT tool that reads or constrains `nVersion` for its own purposes (fee
heuristics, RBF signaling, version-gated features) now has to special-case one specific value
forever, to solve what is fundamentally a one-bit "which side of the fork" question.

**4. The readiness claims outrun the implementation.** RIP-0009's own text states that the Layer 2
peer-punishment fix — the change from `TX_CONSENSUS` to `TX_RECENT_CONSENSUS_CHANGE`, which is what
prevents honest lagging nodes from being discouraged within hours — is "not yet staged" in the
reference implementation; only the harsher, punitive behavior is currently committed. A document
that identifies its own unresolved DoS-adjacent gap shouldn't, in the same breath, present a
"Verification" section implying complete, passing coverage. We'd want that fix landed and tested
before any production-readiness claim, not after.

**5. This idea started with us, and we dropped it before writing any implementation.** RIP-0009
cites a commit in a personal, unsigned fork (`takologi/rincoin`) as the origin of the RIN3 constant.
That attribution is accurate, and worth stating plainly rather than leaving implicit: the fixed-
`nVersion`-marker idea was introduced first by this project's own maintainer, in an early exploratory
commit, before RIP-0009 existed. It was abandoned at the design stage — before any implementation was
built on it, let alone shipped — once we judged permanently repurposing a shared transaction field
for one narrow job to be improper practice, for the same reasons laid out in point 3 above. RIP-0009
revives an idea we ourselves originated and then rejected; citing it as prior art is accurate, but
it isn't evidence the idea holds up — the people who first proposed it are the same people now
declining to use it.

## What we'll do instead

As detailed in [`consensus-transition.md §6`](consensus-transition.md#6-transaction-replay-a-sighash-level-fork-identifier), our
chosen direction is a **sighash-level fork identifier** rather than a transaction-version marker: a
`sig_fork_id` value mixed into the signature hash itself, derived from the same `branch_id`/`fork_no`/
`scenario_id` already defined for block separation. Unlike a required `nVersion` value, this doesn't
depend on the *other* chain rejecting anything — a signature computed our way is cryptographically
invalid under any other chain's hashing rule by construction, not by policy. Scope for height 840,000
covers legacy and SegWit v0 spends only, with Taproot and MWEB coverage following before their own
(much later) activation heights — see [`replay-protection-plan.md`](replay-protection-plan.md). We
will not bundle this into the monetary-scenario decision, and if it can't be genuinely ready — spec,
implementation, tests, and real ecosystem adoption time — before H1, we fall back to an operational
runbook instead of rushing consensus code.

If Aevust or anyone else wants to propose replay protection decoupled from one specific monetary
schedule, scoped as its own reviewable change, we'd welcome it — the peer-management engineering in
RIP-0009 (defense-in-depth mempool checks, capability bits over version floors, non-punitive lagging-
peer classification) is genuinely good and could usefully inform that design.

## Bottom line

We are not adopting RIP-0002/S7 as the Rincoin Core monetary schedule — it fails our own
bounded-issuance requirement unless RIP-0005 becomes a real, ratified consensus rule first. We are
not adopting RIP-0009/RIN3 as specified — it is bundled to a disqualified monetary schedule,
permanently repurposes a transaction-wide field to do a narrower job, and its own safety-critical fix
is unstaged. We recognize genuine merit in parts of RIP-0009's peer-management design and have
carried it into our own direction: a sighash-level fork identifier, decoupled from the monetary
decision, scoped to what can actually be ready by H1 — see
[`consensus-transition.md §6`](consensus-transition.md#6-transaction-replay-a-sighash-level-fork-identifier) and
[`replay-protection-plan.md`](replay-protection-plan.md).
