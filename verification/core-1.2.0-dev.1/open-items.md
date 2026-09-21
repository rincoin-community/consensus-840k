# Open items and limits of this evidence

What the evidence in this directory does not cover, stated so that nobody has to guess.

## Not tested

- **Real mining at the transition height on a network with competing hash rate.** Every "longer" or
  "stronger" branch here is a controlled number of regtest blocks at minimum difficulty. Nothing here
  says anything about hash-rate shares or about how long a shared empty continuation lasts in
  practice.
- **Testnet and the preview network as running networks.** Their parameters are unit-tested
  (`s6b_subsidy_tests`, `versionbits_tests`, `rinhash_tests`); no multi-node testnet or preview chain
  was run through its transition height.
- **The terminal height (234,587,500) in a functional test.** It is covered by unit tests of the
  subsidy function only; the functional tests go up to the 0.6 RIN phase.
- **Pool software end to end.** The coinbase constructions of pool software were modelled in
  `feature_s6b_coinbase_flags.py` (flags copied raw, all `coinbaseaux` values wrapped in one push,
  flags ignored); no pool stack was run against the node.
- **External wallets and signers.** Electrum-style wallets, hardware wallets and exchange or pool
  payout systems that sign outside Rincoin Core have to implement the new signature hash themselves;
  none has been tested, because none implements it yet.
- **Other platforms.** Only the Linux x86_64 build (Ubuntu 20.04 variant) was built and tested. The
  aarch64, Windows and Ubuntu 24.04 variants of the release path were not built.
- **Sanitizer builds** (ASan/UBSan) and the fuzz targets were not run for this build.
- **Automatic outbound peer selection of Rin-coin/rincoin** (which asks for service bit 25) was read
  in its source, not exercised; the peer table in the matrix uses manual connections.

## Known limitations of the build

- **Taproot and MWEB are not covered by `sig_fork_id`.** Neither is active on mainnet before heights
  2,161,152 and 2,217,600; both are tracked as follow-up work
  ([`../../technology/replay-protection-plan.md`](../../technology/replay-protection-plan.md)).
- **`libbitcoinconsensus`-style script verification** (the shared library's `verify_script` entry
  points) has no height argument and verifies with the historical signature hash only.
- **A transaction that is unconfirmed when the last block below the transition height connects
  becomes invalid**, and so does one that a reorganization across that height returns to the mempool
  from a block below it. The wallet keeps such a transaction until it is abandoned
  (`abandontransaction`) and sent again; there is no automatic re-signing.
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
