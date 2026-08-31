# S6/b — Functional Test Results

Commit `2cec8c6d9`. Reproduce with:

```
cd rincoin-core && git checkout consensus/s6b-testing
./scripts/build.sh
python3 test/functional/fork_report.py --out-json fork-test-report.json --out-md fork-test-report.md
```

## Fork-scenario tests (single-node and two-node)

```
feature_fork_commitment.py    : pass (2.3s)
feature_fork_subsidy.py       : pass (3.1s)
feature_fork_sig_fork_id.py   : pass (2.9s)
feature_fork_reorg.py         : pass (3.7s)
feature_fork_vs_legacy.py     : pass (3.8s)
feature_fork_vs_aevust.py     : pass (13.4s)
```

All six passed on the first run against this scenario, including the
rewritten `feature_fork_subsidy.py` (below) — no fix cycle was needed this
time, unlike S5/b's MWEB-crossing discovery.

`feature_fork_vs_legacy.py` and `feature_fork_vs_aevust.py` are reused
unmodified from `consensus/s1-testing`; their conclusions (clean divergence
from `v1.1.0` and `v1.0.1`, correct header/full-block asymmetry against the
foreign `Aevust/rincoin` fork) don't depend on the subsidy scenario, same
as already established for S1 and S5/b.

## `feature_fork_subsidy.py`: rewritten, more thorough than S1/S5/b's own

S6/b's regtest phase table (offsets 0/50/100/150/160 past H1) is small
enough that its terminal cutoff — normally the hardest part of any of
these scenarios to reach by mining — is well under `FIRST_MWEB_HEIGHT`
(432). That made it possible to test every phase transition directly,
including the terminal zero phase itself, rather than falling back to a
real-miner consistency check the way S5/b's second boundary had to:

- H1 (400,000,000): overclaim rejected, exact ceiling accepted, zero
  accepted then rolled back.
- H1+50 (200,000,000): overclaim rejected, exact ceiling accepted.
- H1+100 (100,000,000): same.
- H1+150 (60,000,000): same.
- H1+160 (0, the terminal cutoff): confirmed the table's final phase is
  reached and pays exactly zero.

This is stronger functional coverage than either S1's or S5/b's own
subsidy tests (which each only exercise two data points: H1 and one later
boundary) — a direct, deliberate consequence of this scenario's own
regtest table being fully reachable, not extra scope added for its own
sake.

## Full CI functional allowlist

```
159 / 159 passed
```

The complete set of pre-existing, non-fork-specific functional tests, run
unmodified against this branch's binaries — confirms no regression to
ordinary wallet, mempool, P2P, mining, or MWEB behavior.

## `-reindex-chainstate` interaction

Not re-verified independently for this scenario, same reasoning as S5/b's
own annex: the property is architectural (shared, unmodified code), not
scenario-specific. Tracked as a nice-to-have, not a suspected gap.
