# Rincoin Height-840,000 Consensus Transition — Technical Specification

Status: Working specification for Rincoin Community Core 1.2.0 (Revision 6.1). Revision 6.1 leaves
MWEB unactivated on mainnet ([§1](#1-what-changes-at-height-840000-and-what-does-not)). Revision 6.0 gives
transaction replay protection the `SIGHASH_FORKID` form ([§5](#5-transaction-replay-protection-sighash_forkid));
Revisions 5.0 and 5.1 appended a 16-byte identifier to the signature hash instead. Revision 4.0 of
2026-08-16 described a mandatory coinbase-commitment design that is no longer planned.

Date: 2026-09-26 (Revision 5.0: 2026-09-19; 5.1: 2026-09-20; 6.0: 2026-09-21)

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
2. **Transaction signatures** of pre-SegWit and SegWit v0 inputs are replay-protected ones: they
   set `SIGHASH_FORKID` and are hashed with the BIP143 algorithm with the fork ID 840
   ([§5](#5-transaction-replay-protection-sighash_forkid)).
3. **Block 840,000 only** carries one additional coinbase-value condition
   ([§3](#3-the-coinbase-condition-in-block-840000)).

Not tied to the height, but part of the same release: **MWEB is not activated on mainnet.** Its
deployment inherited from Litecoin would have activated it by height at its timeout, 2,427,264, even
without signalling. In line with other implementations of this chain, the mainnet deployment is set
to never activate, so MWEB transactions stay non-standard and MWEB data in a block stays invalid, as
they are today. In 2026 Litecoin had to fix a consensus flaw in its MWEB validation that allowed the
MWEB balance to be broken on its mainnet, and to freeze the affected outputs (Litecoin Core 0.21.5.4
to 0.21.5.6, whose fixes this release includes); activating MWEB on Rincoin is left to a later,
deliberate decision. The test networks keep
their MWEB deployment so that it stays testable.

Unchanged: proof of work (RinHash), block header format, transaction serialization,
transaction `nVersion` semantics, standardness of `nVersion` (1 and 2), witness commitment rules,
SegWit, the Taproot deployment schedule inherited from Litecoin (height 2,161,152, not active before
840,000), and the validity of every block and signature below
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
| this transition (subsidy, `SIGHASH_FORKID`, activation-block coinbase rule), minimum peer version 70018 | 840,000 | 8,400 | 840 | 840 |
| 2 RIN / 1 RIN / 0.6 RIN | 2,100,000 / 4,200,000 / 6,300,000 | 21,000 / 42,000 / 63,000 | 2,100 / 4,200 / 6,300 | 2,100 / 4,200 / 6,300 |
| zero subsidy | 234,587,500 | 2,345,875 | 234,587 | 234,587 |
| Taproot deployment start / timeout | 2,161,152 / 2,370,816 | 20,160 / 22,176 | 2,160 / 2,304 | always active |
| MWEB deployment start / timeout | never activated | 22,176 / 24,192 | 2,160 / 2,304 | 2,160 / 2,304 |

Regtest deliberately keeps the upstream regtest conventions for the buried deployments, Taproot and
difficulty, because the inherited test suite depends on them; everything that belongs to this
transition is scaled like on the other test networks.

A version-bits state changes only on a window boundary (mainnet 8,064 blocks, testnet 2,016, preview
and regtest 144), and the windows are not scaled. The scaled start and timeout heights of the two
deployments are therefore rounded down to a multiple of the network's window, with at least one
window between them; the table shows the resulting heights (the mainnet heights already are
multiples of 8,064; the test networks derive MWEB's from the Litecoin mainnet heights 2,217,600 and
2,427,264). On every test network the timeout is exactly one window after the start, and
a height-based deployment locks in at its timeout even without signalling, so the activation
heights are fixed: Taproot is active from 24,192 on testnet and from 2,448 on preview; MWEB from
26,208 on testnet and from 2,448 on preview and regtest. The unrounded values and the derivation
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
provided by the block-840,000 condition; separation of transactions is provided by the
replay-protected signature hash ([§5](#5-transaction-replay-protection-sighash_forkid)).

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

## 5. Transaction replay protection: `SIGHASH_FORKID`

From height 840,000 Rincoin Community Core uses the replay-protected signature hash that Bitcoin
Cash introduced in 2017 and that Bitcoin Gold deployed on a chain with SegWit. The construction is
theirs; only the fork ID and the activation height are Rincoin's. Software that supports Bitcoin
Gold or Bitcoin Cash already contains it.

The alternative of a required transaction version (the RIN3 rule of RIP-0009) is assessed in
[`response-to-rip-0009.md`](response-to-rip-0009.md) and compared against the released code in
[`replay-protection-comparison.md`](replay-protection-comparison.md).

### 5.1 Flag and fork ID

| Item | Value |
|---|---|
| Flag in the hash-type byte of a signature | `SIGHASH_FORKID` = `0x40` |
| Fork ID | `840` (`0x000348`), a 24-bit number, the same on every network |
| Hash type that ends the signature-hash preimage | four bytes, little-endian: `hash-type byte \| (fork ID << 8)` |
| ... for a `SIGHASH_ALL` signature | `0x00034841`: the preimage ends in `41 48 03 00`, the signature ends in `0x41` |
| Flag and fork ID as one number, as some software is configured (for example `fork_id` in the `coins` file of Komodo DeFi Framework) | `0x00034840` |
| For comparison | Bitcoin Cash uses fork ID `0`, Bitcoin Gold `79` |

The fork ID is a static consensus parameter compiled into the node. It is not serialized into any
block and does not depend on the software version, the signalling tag, pool configuration, or the
presence of any marker. It is not zero, because with zero a SegWit v0 signature made for this chain
would also verify under the unchanged rules, and it is below 2^23, so that the shifted value is a
positive number in a signed 32-bit integer, which is how several implementations hold it. `840`
stands for the activation height in thousands; a later scheduled fork would take its own value the
same way.

Earlier constructions are not valid under this specification: the 8-byte identifier of the
testing-mode branches of August–September 2026, and the 16-byte identifier that Revisions 5.0 and
5.1 of this document appended after the hash type.

### 5.2 The signature hash

For every ECDSA signature that is evaluated by `OP_CHECKSIG`, `OP_CHECKSIGVERIFY`,
`OP_CHECKMULTISIG` or `OP_CHECKMULTISIGVERIFY`, in a pre-SegWit script or a SegWit v0 script, in a
block at height ≥ 840,000:

1. **The flag is mandatory.** A non-empty signature whose hash-type byte does not have
   `SIGHASH_FORKID` set is a **script error**: the script fails as a whole, and not merely with a
   false result that a following `OP_NOT` could turn into success. An empty signature (the
   conventional placeholder for "not signed") remains an ordinary failed check, as before.
2. **The digest is the BIP143 one for every input,** pre-SegWit inputs included, so every signature
   commits to the amount of the output it spends. The script code is the one the script version
   defines: for SegWit v0 as in BIP143; for a pre-SegWit script, the executed script from the most
   recent `OP_CODESEPARATOR` on, with the signature being checked removed, as before, and
   serialized as it is (any later `OP_CODESEPARATOR` is not stripped, as in BIP143). For the
   standard pre-SegWit forms that is the `scriptPubKey` (P2PK, P2PKH, bare multisig) or the
   `redeemScript` (P2SH).
3. **The hash type that ends the preimage carries the fork ID** in its upper three bytes
   ([§5.1](#51-flag-and-fork-id)); the low byte is the hash-type byte of the signature and selects
   the BIP143 mode as usual.

All hash types (`SIGHASH_ALL`, `SIGHASH_NONE`, `SIGHASH_SINGLE`, each with or without
`SIGHASH_ANYONECANPAY`) are covered. Only the requirement to set the flag is a consensus rule; the
other checks of a signature's encoding (defined hash types, public-key formats) remain relay
policy, as they have always been. The reference for every detail is the Bitcoin Gold
implementation.

**`SIGHASH_SINGLE` without a matching output.** In the historical pre-SegWit serialization such a
signature is computed over the constant digest `1`, so it fits any transaction on any chain. From
height 840,000 that digest is out of reach: a signature without the flag is a script error, and
one with the flag is hashed the BIP143 way, where this case is an ordinary signature that commits
to no output.

Validation below 840,000 is unchanged in every respect. There the bit `0x40` in a hash-type byte
has no meaning to consensus, and a signature is hashed the historical way whatever that byte says,
so no historical block is affected.

### 5.3 Activation and both directions

The rule is keyed to the height of the block that contains the transaction. In a block at height
≥ 840,000 every evaluated ECDSA signature must be a replay-protected one; in a block below 840,000
every signature is verified the historical way. Both directions therefore hold by construction:

- a transaction signed for the new rule fails signature verification under the historical rule
  (unchanged software and any implementation that does not apply the same fork ID);
- a transaction signed the historical way is a script error in any Community Core block at or
  above 840,000.

A node's mempool evaluates transactions against the height of the next block (tip height + 1). A
transaction signed for the new rule is rejected while the next block height is below 840,000
(`new-style-sig-fork-id`); one signed the historical way is rejected once the next block height
reaches 840,000 (`old-style-sig-fork-id`). Such rejections are classified as a recent consensus
change, not as misbehavior, so honest peers relaying pre-fork residue are not penalized. Unconfirmed
transactions with historical signatures that are still in a node's mempool when the boundary is
crossed are removed and must be re-signed by their wallets; the same applies in the opposite
direction after a reorganization back below the boundary. The script-validation cache includes the
activation state in its key, so a result cached under one regime is never reused under the other.

### 5.4 Signing in Rincoin Community Core

The Core wallet, `signrawtransactionwithwallet`, `signrawtransactionwithkey`, the PSBT RPCs
(`walletprocesspsbt`, and any path that fills PSBT signatures) sign for the regime of the next
block height, without any fallback to the historical signature once the next block height is
840,000 or more. `rincoin-tx`, which has no chain state, takes an explicit signing height
(`-signheight=<n>`) and otherwise signs the historical way.

The same regime applies wherever Core only looks at signatures that somebody else made: when a
second party adds its signature to a partially signed multisig transaction, in
`combinerawtransaction`, and when `finalizepsbt`, `analyzepsbt` or the GUI decide whether the
signatures of a PSBT are complete. A signature is recognized only under the rule it was made for.

Two things are visible to users of the RPC interface. Decoded scripts name the new hash types
(`[ALL|FORKID]` and so on), and the `sighashtype` arguments accept those names from the transition
height on, where the flag is added whether it is named or not. And because the signature hash now
commits to the amount of every input, an output that the caller describes in `prevtxs`
(`signrawtransactionwithkey`, `signrawtransactionwithwallet`, `rincoin-tx`) needs its `amount` also
when it is a pre-SegWit output; for coins that the wallet or the node can see, nothing changes.

### 5.5 What is and is not covered

Only signature checks (`OP_CHECKSIG`, `OP_CHECKMULTISIG` and their `VERIFY` forms, in pre-SegWit and
SegWit v0 scripts) are affected. A transaction whose inputs require no signature — for example a
spend of an anyone-can-spend output or of a script satisfied by a hash preimage alone — is not
affected and can be valid on both continuations; no new restriction is placed on such scripts.
Coinbase transactions have no signed inputs. Taproot (witness version 1) is not active on mainnet
before height 2,161,152 and MWEB is not activated there at all; neither is covered by this replay
protection, and each will receive its own treatment before any activation. Replay protection is therefore a property of signed spends, not an absolute
guarantee about every conceivable transaction.

### 5.6 External signers and integrators

Every piece of software that produces Rincoin signatures has to produce the signatures of §5.2 from
height 840,000 and know which regime applies: Electrum-style wallets (including Electrin), swap
software, exchange and pool payout systems that sign outside Rincoin Core, PSBT tooling, and
libraries. What it needs is the flag, the fork ID `840`, the BIP143 digest for every input (and
therefore the amount of every input), and the height. Software that supports Bitcoin Gold has all
of it except the two numbers; where the flag and the fork ID are configured as one number, that
number is `0x00034840`. A signer that cannot learn the current height (offline signing, PSBT
without height information, software with a static per-coin configuration) has to be told the
regime, or switched, at the transition. Transactions that are signed in advance and kept for later
do not survive the transition. No hardware wallet supports Rincoin today; the form is the one
their generic coin definitions express for Bitcoin Gold (a fork ID and BIP143 for every input).
Software that only verifies, indexes or relays (Fulcrum-style servers, explorers, stratum-only
miners, proxies) needs no signature change. This is a real ecosystem cost of replay protection,
and the reason the specification is published before the release.

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
such as `(dev.2)`); the version increase is diagnostic, the schedule above is unchanged, and no
service bit is introduced.

## 8. Release status and safeguards

- As of 2026-09-19 no 1.2.0 build has been published. The public branch `consensus/s6b-testing`
  (commit `1e5a4201d`, 2026-09-05) is the earlier testing-mode implementation: it contains the S6/b
  subsidy and an earlier form of replay protection, but also the superseded `RINF` commitment, synthetic test constants, a
  mainnet start guard and its own test suite. Its results apply to that branch only.
- A 1.2.0 development build, labelled `v1.2.0-dev.2`, has been built and tested by Rincoin
  Community Forge on a consensus branch based on `dev` (state of 2026-09-21; the executed tests and
  their results are in [`../verification/core-1.2.0-dev.2/`](../verification/core-1.2.0-dev.2/)).
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
- Activate or reschedule Taproot, or activate MWEB, as part of this change.
- Claim a release is ready without executed, reviewable evidence for the exact published constants.

## 11. Reviewing this specification

Consensus-critical claims should be checked against the 1.2.0 source and its test vectors once
published, and against the S6/b specification's frozen subsidy vectors in
[`../analysis/data/`](../analysis/data/). Report defects with the affected height, the expected
and actual behavior, and reproduction steps through the routes in the
[coordination notice](../coordination-notice.md). Participating in review does not imply support
for activation.
