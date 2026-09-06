# S1 — Open Items

Everything in this document is currently true and unresolved. Nothing here is
counted as passed or covered in the summary or the acceptance matrix.

## Blocking, before this document can leave draft status

1. **Cross-implementation producer × validator matrix.** The two existing
   hand-written scripts (`feature_fork_vs_legacy.py`, `feature_fork_vs_aevust.py`)
   only cover 3 of the possible producer/validator pairs, and only in one
   direction each. The planned `test/fork_interop_matrix.py` runs every pair
   in both directions, against the full frozen-vector catalog, for any set of
   binaries supplied to it — not yet built.
2. **Two commitment test-vector gaps**, `FC-N08` (correct payload plus a
   trailing separate script operation) and the `FC-N14` duplicate-detection
   variant — see [`commitment-test-vectors.md`](commitment-test-vectors.md).

## Done since the previous draft

- **CI is green.** `consensus/s1-testing` at `73eb5b3ce` has a fully passing
  CI run
  ([run 33994483614](https://github.com/rincoin-community/rincoin-core/actions/runs/33994483614)):
  all three jobs (`unit+functional`, `asan+ubsan`, `fork-scenario-tests`)
  succeeded. This is no longer an open item.
- **A fourth real bug, found by CI's own first full functional-test run, now
  fixed.** With the previous round's fixes in place, CI got far enough to
  actually run the functional suite for the first time and immediately hit a
  different failure: `test_runner.py --ci` calls `check_script_list(fail_on_warn=True)`,
  which `sys.exit(1)`s the moment any `.py` file in `test/functional/` isn't
  registered in `ALL_SCRIPTS` or `NON_SCRIPTS`. The six `feature_fork_*.py`
  scripts and `fork_report.py` (added by this branch's own fork-testing
  framework) were never registered — they're deliberately run through the
  separate `fork-scenario-tests` CI job instead — so this silently hard-failed
  the `unit+functional` job before a single test ran, on every push since the
  very first one. It surfaced behind a benign-but-confusing Bash 5.2 artifact
  (`pop_var_context: head of shell_variables not a function context`, an
  `errexit`-unwind message unrelated to the real cause) that had to be looked
  past to find the actual `sys.exit(1)`. Fixed by adding all seven files to
  `NON_SCRIPTS`; reproduced the failure and confirmed the fix locally before
  pushing.
- **`feature_taproot.py` CI-runner flake, confirmed not a real bug.** Once the
  above fix let the full functional suite actually run, `unit+functional`'s
  first attempt failed on `feature_taproot.py`'s `sync_blocks()` assertion (a
  node transiently reporting zero peers) — identically on all three scenario
  branches, clustered with the suite's other heaviest "tail" tests
  (`feature_pruning.py`, `feature_dbcrash.py`, `rpc_bind.py`), consistent with
  GitHub Actions runner resource contention rather than a code defect (none
  of this round's fixes touch P2P peer/ban logic). Confirmed by `gh run
  rerun --failed`: a clean pass with no further changes.
- **Three real bugs found by the previous CI run, all fixed.** CI run
  33423822277 (commit `a8617fc73`) actually concluded and failed; root cause
  was tracked down rather than guessed at:
  1. The mainnet guard (added to cover Open Risk R6, `rincoin-tx` signing
     mainnet-looking transactions offline) had been placed in
     `AppInitRawTx()`, firing for every `rincoin-tx` invocation and breaking
     the tool's entire pre-existing `bitcoin-util-test.py` suite. Moved into
     `MutateTxSign()` specifically -- scoped to the signing command, the
     actual risk -- and the test harness now sets
     `RINCOIN_TESTING_ALLOW_MAINNET=1` for its own child processes
     (`os.environ.setdefault`, not an override) since its own sign-command
     cases exercise that path purely offline.
  2. A genuine heap-use-after-free race in `ConnectBlock()`
     (`src/validation.cpp`): `txsdata` was declared *after* `control`, so on
     an early return between `control.Add()` and `control.Wait()` (e.g. a
     transaction failing validation partway through the loop), C++'s
     reverse-declaration-order destruction freed `txsdata` before `control`'s
     destructor finished waiting on worker threads that were still reading
     `PrecomputedTransactionData` pointers into it. Caught by CI's ASan leg
     in `txvalidationcache_tests`, not found by inspection; fixed by
     reordering the two declarations. Verified with a full local
     from-scratch clang+ASan+UBSan rebuild (matching the CI leg exactly)
     against the entire unit suite: zero AddressSanitizer/LeakSanitizer
     findings.
  3. The "Upload fork scenario report" artifact-name fix from that same round
     (using `github.ref_name` with slashes replaced) itself used
     `replace()`, which is not a real GitHub Actions expression function --
     this made the whole workflow file fail to parse. Fixed by computing the
     sanitized name in an ordinary shell step instead
     (`${GITHUB_REF_NAME//\//-}` via `GITHUB_ENV`).

  Full local re-verification after all three fixes: 532/532 unit tests, all
  6 fork-scenario functional tests, `bitcoin-util-test.py`, all passing.
- **`branch_id` migration.** `chainparams.cpp` and every test that hardcoded
  the earlier ad-hoc value (`6f2908c82838dab02cae3b9e527a600c`) now use the
  published specification's canonical synthetic test value
  (`00112233445566778899aabbccddeeff`, `technology/consensus-transition.md`
  §5), commit `a8617fc73`. Caught and fixed a real fixture collision this
  produced: `feature_fork_commitment.py`'s `WRONG_BRANCH_ID` had (cleverly,
  at the time) been set to this same canonical value specifically because it
  was guaranteed different from the old ad-hoc `FORK_BRANCH_ID` — migrating
  `FORK_BRANCH_ID` onto it silently made the "wrong" value equal the real
  one. Reassigned `WRONG_BRANCH_ID` to the now-retired ad-hoc value instead.
  Full local re-verification after the migration: 532/532 unit tests, all 6
  fork-scenario functional tests, 159/159 CI allowlist tests, all passing.
- **Independent, non-C++ subsidy re-derivation.** `verification/scripts/independently_derive_s1_schedule.py`
  re-derives the full schedule from the published recursive rule without
  importing the C++ implementation (mirroring
  `analysis/scripts/verify_s6b_independently.py`'s existing role for a
  different scenario) and agrees with all 34 applicable rows of
  `analysis/data/S1_normative_test_vectors.csv`. Also fixed a real problem
  this produced: the subsidy-curve figure previously plotted that sparse
  vector file directly, which invented fake multi-million-block flat
  plateaus between its sparse points; the figure now uses this script's dense
  per-epoch output instead.

## Valuable, not blocking

4. **Fresh-genesis IBD test crossing H1.** Everything tested so far uses
   already-running or incrementally-mined nodes; a full initial-block-download
   from genesis across the activation height (including `-prune`/`-reindex`
   variants) hasn't been run as its own test.
5. **Fuzz targets** for the coinbase-commitment parser
   (`src/consensus/fork_commitment.h`) and the `sig_fork_id` sighash-mixing
   path. This repository already has a fuzzing framework wired into CI; these
   would be new targets registered in it, not new infrastructure.
6. **`legacy-1.1` v1.1.1 halt-fix verification.** A separate effort identified
   that the currently-released `v1.1.0`'s failure to halt at the fork height
   (see `functional-test-results.md`) was caused by the halt height only being
   wired for mainnet, and produced a local `v1.1.1` candidate build with a fix.
   That candidate's own regtest behavior needs to be independently confirmed
   and, once the fix is upstreamed, `v1.1.0` in the reference-binary set here
   should be replaced or supplemented with it.

## Optional, flagged rather than silently dropped

7. **Pool coinbase-rebuild rehearsal.** Real pool software (e.g. the
   operator's own `yiimp` deployment) rebuilds the coinbase transaction
   independently of the node — exactly the integration point where a
   commitment can be silently stripped if the pool software isn't aware of
   it. Proposed as a semi-manual annex script given it spans two separate
   repositories, not full CI automation.
8. **DNS seeder bootstrap smoke check** against the operator's
   `rincoin-seeder` deployment, for the same cross-repository reason as
   above.

## Explicitly out of scope, not "open" — see the summary document

Header-level branch isolation, a dedicated P2P branch-declaration message,
staged release-engineering/coordination machinery, and live mainnet
telemetry are not open items — they're deliberately excluded from this
testing effort, not left undone. Reasons are in
[`S1_Consensus_Testing_Summary.qmd`](../S1_Consensus_Testing_Summary.qmd)'s
"Scope: What This Testing Does Not Cover" section.
