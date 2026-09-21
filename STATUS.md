# Current status

Updated 2026-09-21.

- [x] Coordination invitation: published (2026-08-01)
- [x] Economic study summary: first publication (2026-08-02)
- [x] Economic study full: first publication (2026-08-07)
- [x] Technical overview: first publication (2026-08-16); revised 2026-09-19 ([`technology/`](technology/))
- [x] Scenario selection: **S6/b selected by Rincoin Community Forge for its implementation** (2026-09-19); see the [root README](README.md)
- [x] Coinbase commitment specification: published 2026-08-16, **withdrawn 2026-09-19** (no mandatory branch commitment; see [`technology/consensus-transition.md §4`](technology/consensus-transition.md#4-why-there-is-no-mandatory-branch-commitment))
- [x] Header isolation contingency: closed, not adopted (2026-09-19)
- [x] Replay-protection design: the `SIGHASH_FORKID` signature hash of Bitcoin Cash and Bitcoin Gold, specified 2026-09-21 ([`technology/consensus-transition.md §5`](technology/consensus-transition.md#5-transaction-replay-protection-sighash_forkid); it replaces the 16-byte identifier of Revisions 5.0 and 5.1); comparison with the version-marker approach published ([`technology/replay-protection-comparison.md`](technology/replay-protection-comparison.md))
- [x] Assessment of external RIP-0002/RIP-0009 proposals: published (2026-08-16, [`technology/response-to-rip-0009.md`](technology/response-to-rip-0009.md)); kept as published, dated status note added 2026-09-19
- [x] Block-840,000 coinbase condition: fixed 2026-09-19, exact claim `C == F + 4 RIN` ([`§3`](technology/consensus-transition.md#3-the-coinbase-condition-in-block-840000))
- [x] Replay-protection constants: fixed 2026-09-21: flag `0x40`, fork ID `840` (`0x000348`); a `SIGHASH_ALL` preimage ends in `41 48 03 00`; flag and fork ID as one number: `0x00034840` ([`§5.1`](technology/consensus-transition.md#51-flag-and-fork-id)); test vectors to be published with the 1.2.0 source
- [x] Test-network parameters: fixed 2026-09-20 (every scheduled height scaled by the epoch ratio, deployment heights rounded down to the version-bits window; [`§2`](technology/consensus-transition.md#2-the-monetary-rule-s6b))
- [x] Testing-mode implementations of the three candidates: published August–September 2026 (historical; see [`verification/`](verification/))
- [x] Rincoin Community Core 1.2.0 development build (`v1.2.0-dev.2`): built and tested 2026-09-21; evidence in [`verification/core-1.2.0-dev.2/`](verification/core-1.2.0-dev.2/)
- [x] Source of the 1.2.0 development build: published for testing 2026-09-22 as branch [`consensus/840k-s6b`](https://github.com/rincoin-community/rincoin-core/tree/consensus/840k-s6b) of `rincoin-community/rincoin-core` (not a release)
- [ ] Stable 1.2.0 release: planned by 2026-09-30, after verification
- [ ] Coordination with other implementations: planned; no agreement exists yet
