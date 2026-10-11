# Operating through block 840,000 — runbook

Status: Guidance for operators of Rincoin Community Core 1.2.0 and the software around it.
Date: 2026-10-11

This document says what node operators, pools, exchanges, Electrum server operators, wallet
providers and their users should do before, at and after block height 840,000. The rules
themselves are in [`consensus-transition.md`](consensus-transition.md); this is the operational
side. It is written for the case that worries operators most: that the network does not move to
the new rules as one, and two chains continue from height 840,000.

## 1. When

At 2026-10-11 the chain was at height 774,346 and blocks came every 67 seconds on average over
the previous week. At that rate block 840,000 arrives around **2026-12-01**; at the target spacing
of 60 seconds it would be 2026-11-26. Recompute the estimate from your own node in the last
weeks before the height; do not plan to the hour from this page.

## 2. What everyone has to do

- **Run Rincoin Community Core 1.2.0 ([release](https://github.com/rincoin-community/rincoin-core/releases/tag/v1.2.0)) before height 840,000.** Community Core 1.1.0 stops at
  839,999 by design and refuses to start again. Upgrading is a binary replacement: the data
  directory, indexes included, is opened as it is, without a reindex
  ([upgrade test](../verification/core-1.2.0-dev.2/upgrade-test.md)).
- **A node that has already stopped at 839,999 is upgraded the same way.** It has stored the first
  block 840,000 a peer sent it, without connecting it. After the upgrade 1.2.0 connects that block
  if it is valid under the new rules; if it is not (for example one mined with the old subsidy), it
  marks it invalid, stays at 839,999 and continues with the valid chain as soon as a 1.2.0 peer
  offers it. Both cases were tested end to end (the project's test lab, scenario
  `05-legacy-halt-upgrade`).
- **Software that signs Rincoin transactions itself**, outside the Rincoin Core wallet, must sign
  with `SIGHASH_FORKID` and the fork ID 840 for every transaction that confirms at or after height
  840,000 ([§5](consensus-transition.md#5-transaction-replay-protection-sighash_forkid)). Software
  that only asks a 1.2.0 node to sign (`sendtoaddress`, `sendmany`, `send`, the PSBT and raw
  transaction RPCs) needs no change.

## 3. Transactions signed before the height

A signature made under the rules before height 840,000 is invalid in every block from 840,000
on, and the other way round. This affects anything that is signed in advance and broadcast later:

- transactions with a future `nLockTime` or other time locks, signed now for later;
- multisig and PSBT workflows in which some parties sign before the height and the transaction is
  completed or broadcast after it;
- offline or air-gapped signing, where the signing device does not see the current height;
- atomic swaps (Komodo DeFi Framework, BasicSwap) and any protocol with a pre-signed refund or
  timeout transaction.

**What to do.** Settle such transactions well before the height, or re-sign them after it. For
atomic swaps, stop opening new swaps some hours before the height and resume once the new chain is
established; a swap whose refund was signed before the height cannot use that refund after it.
A wallet transaction that is still unconfirmed when the height is reached is dropped from the 1.2.0
mempool; its coins can be spent again right away, and the wallet keeps the old transaction until it
is abandoned (`abandontransaction`).

## 4. Pools

- Run 1.2.0 under the pool. Pool and mining software needs **no change**: proof of work, block
  header, stratum and `getblocktemplate` are unchanged. Tested on the preview network through its
  transition with yiimp, cpuminer-opt-rin (pool and solo) and tnn-miner; miningcore was checked by
  reading its code.
- **Block 840,000 must claim exactly its subsidy plus all fees** (4 RIN plus fees). Pool software
  that puts the template's `coinbasevalue` into the coinbase does this by itself. Check your setup if
  it splits the reward into several coinbase outputs, adds or removes template transactions, or
  rounds amounts: in that one block the outputs must add up exactly. Every other block may claim
  less, as before.
- `getblocktemplate` needs the client rules `segwit` and `mweb`, as since 1.0.5 (cpuminer-opt-rin
  in solo mode: `--mweb`; miningcore: `hasMWEB`). MWEB itself stays inactive on mainnet.
- After the height, mine only on a 1.2.0 node. A block template from a node with other rules
  produces blocks the 1.2.0 network rejects.

## 5. Exchanges, custodians and payment services

The risks after a chain split are the ones other coins went through: a minority chain is cheap to
attack with a deep reorganization, and for some hours nobody knows which chain the economy follows.

- **Before the height:** suspend RIN deposits and withdrawals about two hours (some 120 blocks)
  before 840,000. Settle or re-sign anything signed in advance (section 3).
- **At the height:** run at least two 1.2.0 nodes on different networks and compare their best
  block. Check that your block 840,000 claims exactly 4 RIN plus fees and that the transactions
  after it carry signatures ending in `0x41`; both are properties of the 1.2.0 chain only.
- **Resuming:** resume once your nodes agree and the new chain has grown for some hours. For the
  first days require considerably more confirmations than usual, for example 100 to 200 blocks for
  larger deposits, and return to normal as the hash rate settles.
- **Replay:** transactions signed by 1.2.0 are invalid on any chain with other signature rules and
  the other way round, so coins do not need a separate splitting step. A transaction whose inputs
  need no signature at all is not protected; no such output exists on mainnet (measured on the
  UTXO set at height 747,987).
- **Do not credit a deposit seen only on a chain that 1.2.0 does not follow.**

## 6. Electrum servers and light wallets

Light wallets do not check the consensus rules; they follow the chain with the most work among the
servers they connect to. After a split this can be the wrong chain. Bitcoin Cash's light wallets
had to ship checkpoints after the 2018 split for exactly this reason.

- **Server operators:** run Fulcrum on a 1.2.0 node, and only on one. A Fulcrum server behind a
  node with other rules serves the other chain to every wallet that connects. Fulcrum's peer
  discovery checks the genesis block, which the other implementations share, and the block header
  eleven blocks below its own tip; a server on another chain is therefore dropped only once the
  chains differ by more than eleven blocks, and not while they still share empty blocks. For the
  first hours after the height set `peering = false` (keeping `announce` as you like), or check the
  peer list (`FulcrumAdmin peers`) and remove servers you cannot vouch for.
- **Electrin users:** keep the default servers, which run on 1.2.0. An Electrin release with a
  checkpoint above 840,000 follows once the new chain exists; install it.
- **Komodo DeFi Framework and other wallets with configured server lists:** use servers that run
  on 1.2.0.

## 7. If a node is on the wrong chain

`getchaintips` shows the branches a node knows. A 1.2.0 node never connects a block that breaks
the new rules, but it can sit on a branch that has not broken them yet (empty blocks are valid
under several rule sets) and switch when that branch does. If a node stays behind its peers:

1. compare `getbestblockhash` with your other 1.2.0 nodes and with the block hashes the project
   publishes after the height;
2. look for `bad-cb-amount-transition`, `Signature must use SIGHASH_FORKID` or
   `old-style-sig-fork-id` in `debug.log`; they name blocks and transactions of another rule set;
3. connect it to known 1.2.0 nodes (`addnode`). In an emergency `invalidateblock <hash>` on the
   first block of the wrong branch and `reconsiderblock` once it is resolved.

A node that ran other software past the height and is then switched to 1.2.0 on the same data
directory keeps the blocks that software connected. 1.2.0 moves to its own chain by itself, once
that chain has more work, when the old software never received a block of that chain. If it did,
the old software stored that block as invalid and 1.2.0 keeps the mark; then either

- start the node once with `-reindex`, which checks the stored blocks again under the 1.2.0 rules
  (on mainnet this takes hours), or
- run `invalidateblock` with the hash of block 840,000 on the node's current chain
  (`getblockhash 840000`) and `reconsiderblock` with the hash of block 840,000 of the 1.2.0 chain,
  then restart the node or let it reconnect to its peers.

## 8. Test networks

Testnet reaches the transition at height 8,400, the preview network and regtest at 840. The
testnet of Rincoin Community Core shares its genesis block, message start and port with the testnet
of another implementation, but not its parameters: a 1.2.0 testnet node rejects that chain from its
first block with witness data, as SegWit activates at height 265 on Community Core's testnet. Expect
foreign peers on testnet; they do not affect mainnet.
