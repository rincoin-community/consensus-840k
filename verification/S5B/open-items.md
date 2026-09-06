# S5/b — Open Items

Everything in this document is currently true and unresolved. Nothing here
is counted as passed or covered in the summary or the acceptance matrix.

## Inherited from S1, not new to this scenario

1. **Two commitment test-vector gaps**, `FC-N08` (correct payload plus a
   trailing separate script operation) and the `FC-N14` duplicate-detection
   variant (correct + wrong-`branch_id`, as opposed to the covered
   correct + wrong-`scenario_id` case) — see
   [`commitment-test-vectors.md`](commitment-test-vectors.md). Since
   `src/consensus/fork_commitment.h` and its test suite are shared,
   unmodified infrastructure, these gaps apply identically to S1 and to
   this scenario; closing them once closes them for both (and for S6/b).
2. **Cross-implementation producer × validator matrix.** The two existing
   hand-written scripts (`feature_fork_vs_legacy.py`, `feature_fork_vs_aevust.py`)
   cover a handful of producer/validator pairs, each in one direction. The
   planned `test/fork_interop_matrix.py` (see S1's own open items) would
   serve all three scenario branches without being rewritten per branch —
   still not built.

## Specific to this scenario

3. **Per-scenario `-reindex-chainstate` re-verification.** S1's own
   empirical check (mine past H1, `-reindex-chainstate`, compare tip and
   `verifychain`) was not independently re-run for S5/b. The property being
   checked is architectural (shared, unmodified code), not scenario-specific,
   so this is a nice-to-have re-confirmation, not a suspected gap.

## Done since the previous draft

- **CI is green.** This branch at `b40c765ff` has a fully passing CI run
  ([run 33994483619](https://github.com/rincoin-community/rincoin-core/actions/runs/33994483619)):
  all three jobs succeeded. This is no longer an open item.
- **A fourth real bug, found by CI's own first full functional-test run, now
  fixed.** Cherry-picked from `consensus/s1-testing`: `test_runner.py --ci`
  was hard-failing the `unit+functional` job before any test ran, because the
  fork-testing framework's own script files weren't registered in
  `test_runner.py`'s `NON_SCRIPTS` list. Fixed by registering them. See
  [`S1/open-items.md`](../S1/open-items.md) for the full root-cause detail.
- **`feature_taproot.py` CI-runner flake, confirmed not a real bug.** Once
  the above fix let the functional suite run, `unit+functional`'s first
  attempt failed on a `sync_blocks()` peer-count assertion — the same test,
  same assertion, on all three scenario branches simultaneously, consistent
  with CI-runner resource contention rather than a code defect. Confirmed by
  `gh run rerun --failed`: a clean pass with no further changes.
- **Three real bugs found by CI, all fixed.** Cherry-picked from
  `consensus/s1-testing` (its own CI run 33423822277 on commit `a8617fc73`
  actually concluded and failed): a mainnet-guard scoping bug that broke
  `rincoin-tx`'s own test suite, a genuine `ConnectBlock()`
  heap-use-after-free race caught by CI's ASan leg (fixed by reordering two
  local-variable declarations so destruction order matches the code's
  documented lifetime requirement), and an invalid GitHub Actions expression
  (`replace()`, not a real function) in the CI artifact-naming fix from the
  same round. The mainnet guard's error text and doc comment, which had
  said "S1 scenario" verbatim from the cherry-pick, were corrected to S5/b.
  Full local re-verification: 532/532 unit tests, all 6 fork-scenario
  functional tests, `bitcoin-util-test.py`, all passing. See
  [`S1/open-items.md`](../S1/open-items.md) for the full root-cause detail.

## Optional, tracked not silently dropped

4. **Pool coinbase-rebuild rehearsal** and **DNS seeder bootstrap smoke
   check** — same status as S1's own open items (not yet done, cross-repo,
   proposed as semi-manual annex scripts).

## Explicitly out of scope, not "open"

Header-level branch isolation, a dedicated P2P branch-declaration message,
staged release-engineering/coordination machinery, and live mainnet
telemetry are deliberately excluded from this testing effort — same
reasoning as S1's own summary document, unrelated to which subsidy
scenario is compiled in.
