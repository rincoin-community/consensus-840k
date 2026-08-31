# S6/b — Open Items

Everything in this document is currently true and unresolved. Nothing here
is counted as passed or covered in the summary or the acceptance matrix.

## Inherited from S1, not new to this scenario

1. **Two commitment test-vector gaps**, `FC-N08` and `FC-N14` — see
   [`commitment-test-vectors.md`](commitment-test-vectors.md). Shared,
   unmodified infrastructure; closing them once closes them for all three
   scenario branches.
2. **Cross-implementation producer × validator matrix.** Same status as
   S1's and S5/b's own open items — `test/fork_interop_matrix.py` is not
   yet built; the two narrower hand-written comparisons stand in for it.

## Specific to this scenario

3. **CI result on the pushed commit.** This branch is pushed to
   `rincoin-community/rincoin-core` at `4b05eda72`
   ([run 33436296904](https://github.com/rincoin-community/rincoin-core/actions/runs/33436296904)),
   but that run had not concluded as of this draft — everything above was
   verified locally. Update `build-manifest.json`'s
   `ci_run_status_at_time_of_writing` and this item once it has.
4. **Per-scenario `-reindex-chainstate` re-verification.** Not
   independently re-run for S6/b; architectural property, not
   scenario-specific.
5. **Regtest/testnet/preview's own small-scale phase table** (offsets
   0/50/100/150/160) is an independently *chosen* schedule, not derived
   from a real published specification for a "test network" — unlike the
   mainnet table, there's no external document to cross-check it against
   beyond internal consistency (which the unit tests do check: strictly
   decreasing, final phase is zero). This is expected and fine for a
   testing-only network, but noted for completeness since it differs in
   kind from how every other frozen vector in this project traces back to
   a published source.

## Done since the previous draft

- **Three real bugs found by CI, all fixed.** Cherry-picked from
  `consensus/s1-testing` (its own CI run 33423822277 on commit `a8617fc73`
  actually concluded and failed): a mainnet-guard scoping bug that broke
  `rincoin-tx`'s own test suite, a genuine `ConnectBlock()`
  heap-use-after-free race caught by CI's ASan leg (fixed by reordering two
  local-variable declarations so destruction order matches the code's
  documented lifetime requirement), and an invalid GitHub Actions expression
  (`replace()`, not a real function) in the CI artifact-naming fix from the
  same round. The mainnet guard's error text and doc comment, which had
  said "S1 scenario" verbatim from the cherry-pick, were corrected to S6/b.
  Full local re-verification: 532/532 unit tests, all 6 fork-scenario
  functional tests, `bitcoin-util-test.py`, all passing. See
  [`S1/open-items.md`](../S1/open-items.md) for the full root-cause detail.

## Optional, tracked not silently dropped

6. **Pool coinbase-rebuild rehearsal** and **DNS seeder bootstrap smoke
   check** — same status as S1's and S5/b's own open items.

## Explicitly out of scope, not "open"

Header-level branch isolation, a dedicated P2P branch-declaration message,
staged release-engineering/coordination machinery, and live mainnet
telemetry are deliberately excluded from this testing effort — same
reasoning as S1's own summary document, unrelated to which subsidy
scenario is compiled in.
