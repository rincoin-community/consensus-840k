# Rincoin Height-840,000 Consensus Transition — Technical Specification

Status: Working specification for Rincoin Community Core 1.2.0 (Revision 5.1 — supersedes
Revision 4.0 of 2026-08-16, which described a mandatory coinbase-commitment design that is no
longer planned)

Date: 2026-09-20 (Revision 5.0: 2026-09-19; 5.1 adds the tested state of the development build, the
per-network parameter table and the checking of signatures made by others)

This document describes the rules that Rincoin Community Core 1.2.0 applies from mainnet block
height 840,000, the reasoning behind each rule, and the exact compatibility consequences for
other Rincoin software. It is written so that an independent implementer can reproduce the
behavior. All rules and constants below are fixed as of 2026-09-19; test vectors that pin the
constants will be published with the 1.2.0 source.

**Preference: one common consensus, one chain.** Rincoin Community Forge selected the S6/b monetary
scenario for its own implementation because it is the candidate with the widest achievable
compatibility with other Rincoin software, and it will contact the maintainers of every known
Rincoin implementation with the goal of aligning consensus and signature rules at height 840,000.
No such agreement exists at the time of writing; this document describes Community Core's rules,
not a network-wide agreement.

## 1. What changes at height 840,000, and what does not

Changes (all activated by the height of the block being validated, never by a node's local tip,
calendar date, configuration, or any marker):

1. **Block subsidy** follows the S6/b schedule ([§2](#2-the-monetary-rule-s6b)).
2. **Transaction signatures** for legacy (pre-SegWit) and SegWit v0 inputs are computed over a
   preimage that includes a fixed fork identifier, `sig_fork_id`
   ([§5](#5-transaction-replay-protection-sig_fork_id)).
3. **Block 840,000 only** carries one additional coinbase-value condition
   ([§3](#3-the-coinbase-condition-in-block-840000)).

Unchanged: proof of work (RinHash), block header format, transaction serialization,
transaction `nVersion` semantics, standardness of `nVersion` (1 and 2), witness commitment rules,
SegWit, the Taproot and MWEB deployment schedules inherited from Litecoin (heights 2,161,152 and
2,217,600, neither active before 840,000), and the validity of every block and signature below
height 840,000.

Not introduced: a mandatory coinbase commitment or marker, a required transaction version value
("RIN3"), a header version bit, a new checkpoint, a service bit, or a P2P wire change.

## 2. The monetary rule (S6/b)

S6/b is a bounded, height-only customized halving. The normative subsidy specification, including
frozen test vectors and the derivation of the terminal height, is
[`Rincoin_840k_S6B_Consensus_Change_Specification`](../analysis/Rincoin_840k_S6B_Consensus_Change_Specification.qmd)
(PDF in the same directory). Mainnet maximum subsidy by height:

| Height range | Maximum subsidy |
|---|---|
| below 840,000 | unchanged historical rule (50 RIN halving every 210,000 blocks; 6.25 RIN at 839,999) |
| 840,000 – 2,099,999 | 4 RIN (400,000,000 base units) |
| 2,100,000 – 4,199,999 | 2 RIN |
| 4,200,000 – 6,299,999 | 1 RIN |
| 6,300,000 – 234,587,499 | 0.6 RIN (60,000,000 base units) |
| 234,587,500 onward | 0; transaction fees remain claimable |

Maximum scheduled issuance is exactly 168,000,000 RIN (`16800000000000000` base units; one RIN is
`100000000` base units). Actual issuance can be lower because unclaimed subsidy is forgone, never
carried forward. The rule uses only the block height as input: never UTXO totals, circulating or
lost supply, or price. The final release compiles exactly this schedule; there is no runtime
scenario switch.

Test networks scale every scheduled height by the ratio of their subsidy epoch to mainnet's
210,000 blocks, rounding down; they carry no authority over mainnet. Testnet uses an epoch of 2,100
blocks (1/100), preview and regtest an epoch of 210 blocks (1/1000). Version-bits windows are not
scaled.

| Event | mainnet | testnet | preview | regtest |
|---|---|---|---|---|
| BIP34/65/66, CSV, SegWit | 26,500 | 265 | 26 | upstream regtest conventions (BIP34 500, BIP66 1,251, BIP65 1,351, CSV 432, SegWit from genesis) |
| Dark Gravity Wave | 30,000 | 300 | 30 | disabled |
| this transition (subsidy, `sig_fork_id`, activation-block coinbase rule), minimum peer version 70018 | 840,000 | 8,400 | 840 | 840 |
| 2 RIN / 1 RIN / 0.6 RIN | 2,100,000 / 4,200,000 / 6,300,000 | 21,000 / 42,000 / 63,000 | 2,100 / 4,200 / 6,300 | 2,100 / 4,200 / 6,300 |
| zero subsidy | 234,587,500 | 2,345,875 | 234,587 | 234,587 |
| Taproot deployment start / timeout | 2,161,152 / 2,370,816 | 20,160 / 22,176 | 2,160 / 2,592 | always active |
| MWEB deployment start / timeout | 2,217,600 / 2,427,264 | 22,176 / 24,192 | 2,160 / 2,592 | 2,160 / 2,304 |

Regtest deliberately keeps the upstream regtest conventions for the buried deployments, Taproot and
difficulty, because the inherited test suite depends on them; everything that belongs to this
transition is scaled like on the other test networks.

A version-bits state changes only on a window boundary (mainnet 8,064 blocks, testnet 2,016, preview
432, regtest 144), and the windows are not scaled. The scaled start and timeout heights of the two
deployments are therefore rounded down to a multiple of the network's window, with at least one
window between them; the table shows the resulting heights (the mainnet heights already are
multiples of 8,064). On every test network the timeout is exactly one window after the start, and
a height-based deployment locks in at its timeout even without signalling, so the activation
heights are fixed: Taproot is active from 24,192 on testnet and from 3,024 on preview; MWEB from
26,208 on testnet, 3,024 on preview and 2,448 on regtest. The unrounded values and the derivation
are tabulated in Rincoin Community Core's `doc/rincoin-parameters.md`.

Testnet keeps its genesis block and message start; a testnet chain built under earlier parameters is
not valid under these. The preview network has a new genesis block
(`00004282aaa888c5b7a1bb210464788510d3c5976a8cec49061a3eb49d04ff33`) and is meant to be reset
whenever a rehearsal needs a fresh chain.

On regtest and preview the scaled issuance ceiling (168,000 RIN) is not an exact multiple of the
final phase's subsidy, so the zero-subsidy height is rounded down and 0.3 RIN of the scaled ceiling
stays unclaimable; on testnet and mainnet the division is exact.

The unbounded variant of the same 4 → 2 → 1 → 0.6 RIN path without S6/b's terminal cutoff (S7 in
the monetary analysis) corresponds to the schedule published as Aevust's RIP-0002 and implemented
in Rin-coin/rincoin; our assessment of that proposal, and of the related RIP-0009, is in
[`response-to-rip-0009.md`](response-to-rip-0009.md).

The coinbase rule at every height remains an upper bound, `C ≤ S(h) + F`, with `C` the sum of all
coinbase output values, `S(h)` the maximum subsidy at height `h`, and `F` the sum of the fees of all
non-coinbase transactions in the block as computed by consensus validation. Underclaiming is valid
at every height **except block 840,000** (next section).

Unchanged software (the v1.0.x line) permits 3.125 RIN at height 840,000. Because the coinbase
rule is an upper bound, a block claiming 3.125 RIN or less would satisfy both the old and the new
schedule. This is why block 840,000 needs one additional condition.

## 3. The coinbase condition in block 840,000

Purpose: make the Community Core continuation's block 840,000 invalid under the unchanged rules,
so that no later block can be shared with software still applying the historical schedule. The
condition holds in every validation context — first acceptance, initial block download, reindex,
and reorganization — and it is a permanent consensus rule for that one height, not a checkpoint,
not a local switch, and not a marker in the coinbase.

Definitions (integer base units): `C` = sum of all coinbase output values of block 840,000; `F` =
sum of the fees of all non-coinbase transactions in that block, as computed by consensus
validation; `S_old(840000) = 312,500,000` (3.125 RIN); `S_new(840000) = 400,000,000` (4 RIN).

**Rule (fixed 2026-09-19).** Block 840,000 is valid only if

```
C == F + 400,000,000
```

that is, the coinbase must claim exactly the maximum subsidy plus all fees. A claim one base unit
lower or higher is invalid; the number and layout of coinbase outputs are irrelevant, only their
sum counts. The alternative of accepting any claim above the historical maximum
(`F + 312,500,000 < C ≤ F + 400,000,000`) was considered and not chosen: the exact rule is simpler
to specify and to test, and it is what every template-driven miner produces anyway.

The rule guarantees rejection by unchanged software, which rejects any block-840,000 coinbase with
`C > F + 312,500,000`; both sides compute the same fee total for the same block. It creates no
minimum-claim obligation at any other height. Block templates from Community Core claim the full
amount; validation does not assume that every miner uses Community Core templates. A miner whose
coinbase construction drops fees or underclaims at that one height produces a block that Community
Core rejects; the next valid block resolves it.

Consequences that do not depend on the formulation:

- A block 840,000 mined by unchanged software (claiming at most 3.125 RIN + fees) is invalid for
  Community Core, and every block built on it is invalid for Community Core regardless of
  accumulated work.
- A block 840,000 claiming exactly 4 RIN + fees is valid for Community Core and for the current
  Rin-coin/rincoin implementation (whose block-840,000 rule is the ordinary 4 RIN upper bound),
  provided every other rule of both implementations is satisfied by the block and its history.

## 4. Why there is no mandatory branch commitment

Revision 4.0 required a zero-value `OP_RETURN` coinbase output (`RINF` namespace with
`branch_id`, `fork_no`, `scenario_id`) in every block from 840,000, so that any two new
implementations would reject each other's blocks by construction. This is no longer planned.

The commitment would have forced every pool and solo miner to change coinbase construction, would
have required a `getblocktemplate` extension, and would have made a common chain with any other
new implementation impossible by design even if the consensus rules were otherwise aligned. Given
the goal of coordination, that cost is not justified. Separation from unchanged software is
provided by the block-840,000 condition; separation of transactions is provided by `sig_fork_id`.

What this design guarantees and what it does not:

- Community Core and another new implementation agree on an empty block only if the block's
  entire history and all other rules are valid for both.
- With a full 4 RIN claim, the first empty post-fork blocks can be valid both for Community Core
  and for the current Rin-coin/rincoin implementation, and invalid for unchanged software.
- The first ordinary transaction signed under one implementation's signature rule makes its
  block, and every descendant, invalid for the other implementation. This does not create an
  irrevocable checkpoint and does not guarantee that every alternative empty history is invalid
  forever.
- More accumulated work never legalizes an invalid ancestor; a reorganization can only lead to a
  history that is valid for the validating node.
- Low transaction volume can prolong a shared empty continuation. This is an accepted property.

Blocks that carry a voluntary `RINF`-style output, any other `OP_RETURN` output, or ordinary
`OP_RETURN` transactions are not rejected for that reason. The SegWit witness commitment is a
different mechanism and remains required exactly as before.

## 5. Transaction replay protection: `sig_fork_id`

The alternative of a required transaction version (the RIN3 rule of RIP-0009) is assessed in
[`response-to-rip-0009.md`](response-to-rip-0009.md) and compared against the released code in
[`replay-protection-comparison.md`](replay-protection-comparison.md).

### 5.1 Identifier

`sig_fork_id` is the 16-byte ASCII constant

```
Rincoin-840k-S6b        (hex 52696e636f696e2d3834306b2d533662)
```

The string names the chain, the activation height and the scenario. It is used as is: no hashing,
no derivation, no byte-order conversion. It is a static consensus parameter compiled into the
node, identical on every network, and it is not serialized into any block. It does not depend on
the software version, the signalling tag, pool configuration, or the presence of any marker.

The testing-mode branches of August–September 2026 used a different, 8-byte identifier derived as
`SHA256(branch_id || fork_no || scenario_id)[:8]` from a synthetic `branch_id`; signatures made
that way are not valid under this specification. Test vectors pinning the constant above will be
published with the 1.2.0 source.

### 5.2 Where it enters the signature hash

For every signature check of a legacy (pre-SegWit) input and of a SegWit v0 (BIP143) input in a
block at height ≥ 840,000, the 16 bytes of `sig_fork_id` are appended verbatim as the final field of
the preimage, immediately after the 4-byte little-endian `nHashType`. No length prefix and no
integer reinterpretation are applied. Everything before that point is the unchanged legacy or
BIP143 serialization, so all hash types (`SIGHASH_ALL`, `SIGHASH_NONE`, `SIGHASH_SINGLE`, each with
or without `SIGHASH_ANYONECANPAY`) are covered, including `ANYONECANPAY` variants.

The signature encoding is unchanged: the hash-type byte appended to a DER signature keeps its
existing values. No new hash-type flag (such as Bitcoin Cash's `SIGHASH_FORKID`, `0x40`) is
introduced, so a signature cannot be told apart from an old-style one by inspection; it can only
be verified against one regime.

**`SIGHASH_SINGLE` without a matching output (rule fixed 2026-09-19).** In the legacy
serialization, a `SIGHASH_SINGLE` signature for an input index that has no corresponding output has
historically been computed over the constant digest `1` (the well-known `uint256::ONE` behavior).
That digest does not depend on the transaction, so such a signature would remain valid on both
sides of the fork. From height 840,000, in the legacy (pre-SegWit) script path, checking a
non-empty signature whose hash type is `SIGHASH_SINGLE`, with or without `SIGHASH_ANYONECANPAY`,
for an input index `nIn ≥ vout.size()` is a **script error**: the script fails as a whole, in
`OP_CHECKSIG`, `OP_CHECKSIGVERIFY`, `OP_CHECKMULTISIG` and `OP_CHECKMULTISIGVERIFY` alike, and not
merely a false result that a following `OP_NOT` could turn into success. An empty signature (the
conventional placeholder for "not signed" in multisig) remains an ordinary failed check, as
before. `SIGHASH_SINGLE` with a matching output is unchanged; SegWit v0 and Taproot are unchanged
(their digest constructions have no such case); the hash type itself is not banned. Validation
below 840,000 is unchanged. Mempool admission and every signing path in Core apply the same rule
for the next block height, including across a reorganization of the boundary.

### 5.3 Activation and both directions

The rule is keyed to the height of the block that contains the transaction. In a block at height
≥ 840,000 every legacy and SegWit v0 signature must verify against the preimage with
`sig_fork_id`; in a block below 840,000 every such signature must verify against the historical
preimage. Both directions therefore hold by construction:

- a transaction signed for the new rule fails signature verification under the historical rule
  (unchanged software and any implementation that does not apply the same identifier);
- a transaction signed the historical way fails verification in any Community Core block at or
  above 840,000.

A node's mempool evaluates transactions against the height of the next block (tip height + 1). A
transaction signed for the new rule is rejected while the next block height is below 840,000;
one signed the historical way is rejected once the next block height reaches 840,000. Such
rejections are classified as a recent consensus change, not as misbehavior, so honest peers relaying
pre-fork residue are not penalized. Unconfirmed transactions with historical signatures that are
still in a node's mempool when the boundary is crossed are removed and must be re-signed by their
wallets; the same applies in the opposite direction after a reorganization back below the boundary.
The script-validation cache includes the activation state in its key, so a result cached under one
regime is never reused under the other.

### 5.4 Signing in Rincoin Community Core

The Core wallet, `signrawtransactionwithwallet`, `signrawtransactionwithkey`, the PSBT RPCs
(`walletprocesspsbt`, and any path that fills PSBT signatures) sign for the regime of the next
block height, without any fallback to the historical preimage once the next block height is
840,000 or more. `rincoin-tx`, which has no chain state, takes an explicit signing height
(`-signheight=<n>`) and otherwise signs the historical way.

The same regime applies wherever Core only looks at signatures that somebody else made: when a
second party adds its signature to a partially signed multisig transaction, in
`combinerawtransaction`, and when `finalizepsbt`, `analyzepsbt` or the GUI decide whether the
signatures of a PSBT are complete. A signature is recognized only under the rule it was made for.

### 5.5 What is and is not covered

Only signature checks (`OP_CHECKSIG`, `OP_CHECKMULTISIG` and their `VERIFY` forms, in legacy and
SegWit v0 scripts) are affected. A transaction whose inputs require no signature — for example a
spend of an anyone-can-spend output or of a script satisfied by a hash preimage alone — is not
affected and can be valid on both continuations; no new restriction is placed on such scripts.
Coinbase transactions have no signed inputs. Taproot (witness version 1) and MWEB are not active on
mainnet, are not part of this change, and will receive their own treatment before their own
activation heights. Replay protection is therefore a property of signed spends, not an absolute
guarantee about every conceivable transaction.

### 5.6 External signers and integrators

Every piece of software that produces Rincoin signatures must implement §5.2 and know which
regime applies: Electrum-style wallets (including Electrin), exchange and pool payout systems that
sign outside Rincoin Core, PSBT tooling, and libraries. A signer that cannot learn the current
height (offline signing, PSBT without height information) must be told the regime explicitly.
Hardware wallets that compute the digest in firmware with Bitcoin parameters cannot produce the new
preimage and cannot be used on the Community Core continuation after 840,000 unless their firmware
adds support. Software that only verifies, indexes or relays (Fulcrum-style servers, explorers,
stratum-only miners, proxies) needs no signature change. This is a real ecosystem cost of the
design, and the reason the specification is published before the release.

## 6. Voluntary signalling: `coinbaseaux.flags`

Rincoin Community Core reports a short identifier in the standard BIP22 `getblocktemplate` field
`coinbaseaux.flags`, starting before 840,000. The field's value is a hex-encoded script fragment
that a coinbase builder places in the coinbase `scriptSig` after the BIP34 height push: a single
push opcode followed by the ASCII tag. The tag is `/RCC/` (Rincoin Community Core), encoded as
`052f5243432f` (6 bytes). It identifies the development line, not the individual version, so it
stays stable across releases; its purpose is a rough count of blocks produced with Community Core
templates.

Behavior and limits:

- The node's own miner (`generatetoaddress`, `generateblock`) includes the fragment in every
  coinbase it builds, after the height push and the extra nonce, and keeps it when the extra nonce
  changes. The BIP34 height, the witness commitment, the extra nonce and the 100-byte `scriptSig`
  limit are unaffected.
- A pool that builds its own coinbase must copy the fragment itself. Pool software differs: yiimp
  splices the bytes of `coinbaseaux.flags` verbatim after the height push; cpuminer-opt (solo GBT)
  wraps all `coinbaseaux` members in one additional push; Miningcore honors the field unless
  configured to ignore it; at least one node-stratum-pool variant reviewed earlier ignored it. In
  all of these cases the coinbase remains valid, and the literal ASCII tag remains present when
  the field is honored. Explorers should search for the ASCII tag, not for one exact opcode layout.
- The tag is not a consensus rule: a valid block without it, with another tag, or with a copied
  tag is accepted. It is not cryptographic proof of the software used or of an independent
  operator; a pool can omit or imitate it.
- No identification `OP_RETURN` output is added to the coinbase or to ordinary transactions.

## 7. Node identity and peer policy

Client identity is diagnostic only. Rincoin Community Core reports its name and version in the
P2P subversion string and its protocol version in the version handshake; neither field carries
branch identity, and neither is authentication. The existing per-height minimum peer protocol
version schedule (70017 from genesis, 70018 from height 840,000 on mainnet) is a networking policy
inherited from the 1.1 line: from 840,000, peers announcing a lower protocol version are
disconnected. It does not affect block validity. Rincoin Community Core 1.2.0 advertises protocol
version 70019 and the subversion `/RincoinCommunityCore:1.2.0/` (development builds add a comment
such as `(dev.1)`); the version increase is diagnostic, the schedule above is unchanged, and no
service bit is introduced.

## 8. Release status and safeguards

- As of 2026-09-19 no 1.2.0 build has been published. The public branch `consensus/s6b-testing`
  (commit `1e5a4201d`, 2026-09-05) is the earlier testing-mode implementation: it contains the S6/b
  subsidy and `sig_fork_id`, but also the superseded `RINF` commitment, synthetic test constants, a
  mainnet start guard and its own test suite. Its results apply to that branch only.
- A first 1.2.0 development build, labelled `v1.2.0-dev.1`, has been built and tested by Rincoin
  Community Forge on a consensus branch based on `dev` (state of 2026-09-20; the executed tests and
  their results are in [`../verification/core-1.2.0-dev.1/`](../verification/core-1.2.0-dev.1/)).
  Its source has not been published at the time of writing; it will be published for testing after
  review. It is not production software: it is marked as a pre-release build and it carries an
  explicit safeguard against accidental production use that the stable release removes. Unlike the
  terminal 1.1.x line, it continues past 840,000 under the rules above; there is no
  stop-at-840,000 behavior.
- A stable production release is planned by 2026-09-30, after verification. On 2026-09-19 the
  mainnet height was about 747,250, roughly 92,750 blocks (about 64 days at the 60-second target)
  before 840,000. These are plans and estimates, not readiness statements.

## 9. A future scheduled fork

A later scheduled activation would define its own identifier string in the same style, naming
its own height and scenario, while every historical identifier stays compiled in so that full
validation and reindexing of earlier blocks keep working. No second activation is scheduled.

## 10. What we will not do

- Treat any header bit, protocol version, service flag, or user-agent string as branch
  authentication or as an ownership claim.
- Ship a production binary with a runtime-selectable monetary scenario.
- Require a permanent identifier in every block that would by itself prevent a common chain with
  another implementation whose rules are otherwise aligned.
- Introduce a general minimum or exact coinbase claim beyond the single block-840,000 condition.
- Reuse the transaction `nVersion` field as a mandatory fork marker (the RIN3 rule of RIP-0009);
  see [`response-to-rip-0009.md`](response-to-rip-0009.md) and
  [`replay-protection-comparison.md`](replay-protection-comparison.md).
- Activate, deactivate, or reschedule Taproot or MWEB as part of this change.
- Claim a release is ready without executed, reviewable evidence for the exact published constants.

## 11. Reviewing this specification

Consensus-critical claims should be checked against the 1.2.0 source and its test vectors once
published, and against the S6/b specification's frozen subsidy vectors in
[`../analysis/data/`](../analysis/data/). Report defects with the affected height, the expected
and actual behavior, and reproduction steps through the routes in the
[coordination notice](../coordination-notice.md). Participating in review does not imply support
for activation.
