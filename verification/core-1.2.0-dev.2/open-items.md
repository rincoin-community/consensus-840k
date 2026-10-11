# Open items and limits of this evidence

What the evidence in this directory does not cover, stated so that nobody has to guess.

## Not tested

- **Real mining at the transition height on a network with competing hash rate.** Every "longer" or
  "stronger" branch here is a controlled number of regtest blocks at minimum difficulty. Nothing here
  says anything about hash-rate shares or about how long a shared empty continuation lasts in
  practice.
- **Testnet as a running network.** Its parameters are unit-tested (`s6b_subsidy_tests`,
  `versionbits_tests`, `rinhash_tests`). With this build no testnet chain was run through its
  transition height 8,400; a private testnet chain was later run through it with the `v1.2.0rc1`
  release binaries (see below). The public testnet with other participants was not used. The
  preview network was run through its transition height with real proof of work, pools and miners
  in the project's test lab, with an earlier build of the same rules; not with this one.
- **The terminal height (234,587,500) in a functional test.** It is covered by unit tests of the
  subsidy function only; the functional tests go up to the 0.6 RIN phase.
- **Pool software end to end.** The coinbase constructions of pool software were modelled in
  `feature_s6b_coinbase_flags.py` (flags copied raw, all `coinbaseaux` values wrapped in one push,
  flags ignored); no pool stack was run against the node.
- **External wallets and signers.** Electrum-style wallets, hardware wallets and exchange or pool
  payout systems that sign outside Rincoin Core have to produce the new signatures themselves; none
  has been tested against this build. (The construction itself is checked against signatures of real
  Bitcoin Gold transactions in the unit tests.)
- **Other platforms.** The release build also produced aarch64, Windows, macOS and Ubuntu 24.04
  variants. Only the Linux x86_64 Ubuntu 20.04 variant was tested; the others were built, not run.
- **Sanitizers and fuzzing.** The project's CI ran the unit tests under ASan and UBSan and the
  functional allowlist on a plain build, both passing for the commit the binaries were built from.
  The functional tests did not run under the sanitizers, and the fuzz targets did not run at all.
- **Real wallet files of earlier releases.** The upgrade test left the wallets out on purpose;
  opening a 1.1.0 wallet file with this build was not tested.
- **Automatic outbound peer selection of Rin-coin/rincoin** (which asks for service bit 25) was read
  in its source, not exercised; the peer table in the matrix uses manual connections.

## Covered later with the `v1.2.0rc1` release binaries

Two scenarios of the project's test lab were added after this evidence was taken and run with the
Linux x86_64 binaries of the `v1.2.0rc1` release (2026-10-11). Neither found a defect in Community
Core, and no change to its code came out of them; the corrections made while writing them were to
the scenarios' own expectations.

- **Upgrade of a node halted by Community Core 1.1.0** (`05-legacy-halt-upgrade`, regtest,
  17/17 checks). A 1.1.0 node stops at the last block below the transition height and stores the
  first block above it without connecting it. After a binary swap to 1.2.0 on the same data
  directory, a block valid under the new rules is connected; a block mined with the old subsidy is
  marked invalid (`bad-cb-amount-transition`), the node stays at the last block below the height and
  follows the valid chain as soon as a 1.2.0 peer offers it. Both outcomes survive a restart.
- **Testnet through its transition height** (`06-testnet-transition`, 11/11 checks). Two 1.2.0
  nodes on a private testnet chain built with real proof of work to height 8,404: a payment below
  8,400 is signed with hash type `0x01`, block 8,400 claims exactly 4 RIN plus fees, the payment
  signed at tip 8,399 is confirmed in block 8,400 with `0x41`, a transaction signed before the
  height is refused afterwards (`old-style-sig-fork-id`), payments above confirm with `0x41`, the
  second node follows across the height, and Taproot and MWEB stay inactive. A 1.2.0 testnet node
  connected to a testnet node of another implementation follows that chain to height 5 and rejects
  block 6 (`unexpected-witness`), because SegWit is active there from the start and only from height
  265 on Community Core's testnet.

## Known limitations of the build

- **Taproot and MWEB signatures are not replay-protected.** Taproot is not active on mainnet before
  height 2,161,152 and MWEB is not activated there at all; both are tracked as follow-up work
  ([`../../technology/replay-protection-plan.md`](../../technology/replay-protection-plan.md)).
- **`libbitcoinconsensus`-style script verification** (the shared library's `verify_script` entry
  points) has no height argument and verifies with the historical signature hash only.
- **A transaction that is unconfirmed when the last block below the transition height connects
  becomes invalid**, and so does one that a reorganization across that height returns to the mempool
  from a block below it. The node drops it from the mempool, so its coins can be spent again at once;
  the wallet keeps the old transaction until it is abandoned (`abandontransaction`). There is no
  automatic re-signing.
- **Inherited from upstream 0.21, unrelated to the transition:** `signrawtransactionwithkey`,
  `signrawtransactionwithwallet` and `combinerawtransaction` abort the node
  (`Assertion 'this->txdata' failed` in `CheckSchnorrSignature`) when the transaction they are given
  already carries a signed Taproot input. It takes an authenticated RPC user to trigger, and the same
  happens on the branch before this work. Bitcoin Core fixed it in 22.0 by handling missing
  precomputed data; that fix has not been ported.

## Test-suite baseline, for the record

Two functional tests outside the CI allowlist fail, and fail identically on the branch before this
work: `feature_signet.py` and `p2p_dos_header_tree.py` (both import regtest keys into chains Rincoin
does not define that way: `Invalid private key encoding`). 42 test invocations skip themselves, most
of them the `--descriptors` variants, which this code base does not support, and tests that need
binaries of previous releases.
