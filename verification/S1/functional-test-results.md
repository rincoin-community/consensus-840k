# S1 — Functional Test Results

Commit `a8617fc73`. Reproduce with:

```
cd rincoin-core && git checkout consensus/s1-testing
./scripts/build.sh
python3 test/functional/fork_report.py --out-json fork-test-report.json --out-md fork-test-report.md
```

## Fork-scenario tests (single-node and two-node)

```
feature_fork_commitment.py    : pass (2.4s)
feature_fork_subsidy.py       : pass (2.9s)
feature_fork_sig_fork_id.py   : pass (2.7s)
feature_fork_reorg.py         : pass (3.9s)
feature_fork_vs_legacy.py     : pass (5.0s)
feature_fork_vs_aevust.py     : pass (12.8s)
```

`feature_fork_vs_legacy.py` and `feature_fork_vs_aevust.py` are the current,
hand-written cross-implementation tests. **They are scheduled to be replaced**
by a single, scenario-generic tool (`test/fork_interop_matrix.py`, not yet
built — see [`open-items.md`](open-items.md)) that runs the same producer ×
validator comparison for any set of binaries, so the same tool serves S5/b and
S6/b later without rewriting. Until that tool exists, these two scripts are
the actual cross-implementation evidence for S1, and their content is
summarized below rather than only referenced.

### What `feature_fork_vs_legacy.py` established

- S1 vs. `v1.1.0` (`rincoin-community/rincoin-core`): the older release does
  **not** halt or refuse to extend the chain past height 840,000 on a
  non-mainnet chain — confirmed by running it, contradicting that release's
  own stated branch policy (which turned out to gate the halt height to
  mainnet only). Reported as a finding about that release, not about S1.
- S1 vs. `v1.0.1` (`Rin-coin/rincoin`, no fork awareness at all): clean
  divergence — no crash, no accidental adoption of the S1 chain, confirmed
  directly via `getbestblockhash` on both nodes (they don't even share
  genesis, which was independently verified via RPC rather than assumed).

### What `feature_fork_vs_aevust.py` established

- S1 vs. `Aevust/rincoin@feature/port-sim-v1.0.7` (a foreign, independently
  developed fork, built from a standalone clone outside this repository):
  the foreign branch's headers can become this node's best-known-header, but
  full-block validation rejects it at H1 for a missing/wrong commitment —
  `getbestblockhash` (the validated tip) never adopts it even while
  header-tracking RPCs see it.

## Full CI functional allowlist

```
159 / 159 passed
```

The complete set of pre-existing, non-fork-specific functional tests
(`test/functional/ci_passing_tests.txt`), run unmodified against this branch's
binaries — confirms the branch doesn't regress ordinary wallet, mempool, P2P,
mining, or MWEB behavior. Two test files needed updating not because of a
regression, but because they encode assumptions this branch deliberately
changes: `feature_uacomment.py` (this build always stamps a fixed identifying
comment onto its P2P subversion string) and `feature_config_args.py` (one
sub-test intentionally starts a node on the mainnet chain to test unrelated
config-parsing behavior; this build's mainnet guard now fires first, so the
test sets the guard's environment variable for just that one assertion,
preserving the original check's coverage).

## `-reindex-chainstate` interaction

Verified empirically, not just by reading the code: mined a chain past the
activation height, stopped the node, restarted with `-reindex-chainstate`,
and confirmed an identical tip and a clean `verifychain`. `-reindex-chainstate`
does not re-run the block-acceptance-time consensus checks (a pre-existing,
long-standing Bitcoin Core property shared by every other height-gated
consensus rule already in this codebase, not something specific to this
branch) — closed as verified-non-issue rather than left as an open risk.
