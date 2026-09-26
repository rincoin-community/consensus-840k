# Open items and limits of this evidence

What the evidence in this directory does not cover, stated so that nobody has to guess.

## Not tested

- **Real mining at the transition height on a network with competing hash rate.** Every "longer" or
  "stronger" branch here is a controlled number of regtest blocks at minimum difficulty. Nothing here
  says anything about hash-rate shares or about how long a shared empty continuation lasts in
  practice.
- **Testnet as a running network.** Its parameters are unit-tested (`s6b_subsidy_tests`,
  `versionbits_tests`, `rinhash_tests`); no testnet chain was run through its transition height
  8,400. The preview network was run through its transition height with real proof of work, pools
  and miners in the project's test lab, with an earlier build of the same rules; not with this one.
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
