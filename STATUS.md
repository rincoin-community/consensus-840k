# Current status

Updated 2026-09-20.

- [x] Coordination invitation: published (2026-08-01)
- [x] Economic study summary: first publication (2026-08-02)
- [x] Economic study full: first publication (2026-08-07)
- [x] Technical overview: first publication (2026-08-16); revised 2026-09-19 ([`technology/`](technology/))
- [x] Scenario selection: **S6/b selected by Rincoin Community Forge for its implementation** (2026-09-19); see the [root README](README.md)
- [x] Coinbase commitment specification: published 2026-08-16, **withdrawn 2026-09-19** (no mandatory branch commitment; see [`technology/consensus-transition.md §4`](technology/consensus-transition.md#4-why-there-is-no-mandatory-branch-commitment))
- [x] Header isolation contingency: closed, not adopted (2026-09-19)
- [x] Replay-protection design: `sig_fork_id` specified ([`technology/consensus-transition.md §5`](technology/consensus-transition.md#5-transaction-replay-protection-sig_fork_id)); comparison with the version-marker approach published ([`technology/replay-protection-comparison.md`](technology/replay-protection-comparison.md))
- [x] Assessment of external RIP-0002/RIP-0009 proposals: published (2026-08-16, [`technology/response-to-rip-0009.md`](technology/response-to-rip-0009.md)); kept as published, dated status note added 2026-09-19
- [x] Block-840,000 coinbase condition: fixed 2026-09-19, exact claim `C == F + 4 RIN` ([`§3`](technology/consensus-transition.md#3-the-coinbase-condition-in-block-840000))
- [x] `sig_fork_id` constant: fixed 2026-09-20 as the 16 ASCII bytes `Rincoin-840k-S6b` ([`§5.1`](technology/consensus-transition.md#51-identifier)); test vectors to be published with the 1.2.0 source
- [x] Test-network parameters: fixed 2026-09-20 (every scheduled height scaled by the epoch ratio, deployment heights rounded down to the version-bits window; [`§2`](technology/consensus-transition.md#2-the-monetary-rule-s6b))
- [x] Testing-mode implementations of the three candidates: published August–September 2026 (historical; see [`verification/`](verification/))
- [x] Rincoin Community Core 1.2.0 development build (`v1.2.0-dev.1`): built and tested 2026-09-20; evidence in [`verification/core-1.2.0-dev.1/`](verification/core-1.2.0-dev.1/)
- [ ] Source of the 1.2.0 development build: not yet published; to be published for testing after review
- [ ] Stable 1.2.0 release: planned by 2026-09-30, after verification
- [ ] Coordination with other implementations: planned; no agreement exists yet
