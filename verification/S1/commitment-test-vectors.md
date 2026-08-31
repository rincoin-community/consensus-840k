# S1 — Coinbase Commitment Test Vector Catalog

Cross-reference between the malformed-commitment edge cases and the actual
unit test (`src/test/fork_commitment_tests.cpp`, commit `a8617fc73`) that
exercises each one. Case IDs follow the `FC-Pxx`/`FC-Nxx` convention from
earlier design-audit material for this project, kept here only as a naming
scheme — the expected outcomes below are this specification's own, not
carried over from that superseded draft's mechanism.

## Positive vectors

| ID | Case | Test |
| --- | --- | --- |
| FC-P01 | Exact, correct commitment for the S1 tuple (`branch_id`/`fork_no`/`scenario_id`) | `build_and_parse_round_trip` |

The older draft's catalog also names `FC-P02`/`FC-P03` for other scenarios'
own correct commitments. Not applicable here: a given testing-mode build only
knows its own scenario's tuple at compile time — cross-scenario commitment
recognition was never part of the design (each scenario is a separate binary,
not a runtime option), so there is nothing for this branch to test in that
slot. S5/b and S6/b will each have their own `FC-P01` when their branches
exist.

## Negative vectors

| ID | Case | Test | Status |
| --- | --- | --- | --- |
| FC-N01 | Wrong format version byte | `wrong_format_version_rejected` | Covered |
| FC-N02 | Wrong `fork_no` | `wrong_fork_no_rejected` | Covered |
| FC-N03 | Wrong `scenario_id` | `wrong_scenario_id_rejected` | Covered |
| FC-N04 | Nonzero flags byte | `nonzero_flags_rejected` | Covered |
| FC-N05 | Non-minimal push (`PUSHDATA1` instead of a minimal push) | `non_minimal_push_rejected` | Covered |
| FC-N06 | Truncated payload (27 bytes instead of 28) | `truncated_payload_rejected` | Covered |
| FC-N07 | Extended payload (29 bytes in one push) | `extended_payload_rejected` | Covered |
| FC-N08 | Correct 28-byte payload followed by a **separate trailing operation** in the same script (e.g. an extra pushed byte after the commitment push, not a longer single push) | — | **Not covered — gap** |
| FC-N09 | Correct script, nonzero **output value** (the commitment output itself, distinct from the coinbase's total claim) | `nonzero_commitment_value_rejected` | Covered |
| FC-N10 | Two identical correct commitment outputs (duplicate) | `two_correct_commitments_still_rejected` | Covered |
| FC-N11 | One correct + one wrong-`scenario_id` output (duplicate before per-field match) | `duplicate_commitment_rejected_even_if_one_correct` | Covered |
| FC-N12 | No commitment output at all (missing) | `missing_commitment_rejected` | Covered |
| FC-N13 | Wrong `branch_id` | `wrong_branch_id_rejected` | Covered |
| FC-N14 | One correct + one wrong-`branch_id` output (duplicate before per-field match) | — | **Not separately asserted — minor gap** (the wrong-scenario variant, FC-N11, is covered by the same duplicate-detection code path, so this is very likely already correct behavior; just not independently pinned by its own test case) |
| FC-N15 | A prior/legacy commitment layout without a `branch_id` field | N/A | Not applicable — no such prior format ever existed in this design; specific to the older draft's now-abandoned Rev-2 layout |

**Two genuine gaps identified** (FC-N08, and the FC-N14 duplicate-detection
pinning) — both tracked as outstanding work in
[`open-items.md`](open-items.md). Everything else in the malformed-commitment
catalog is covered and passing as of commit `a8617fc73`.

## `sig_fork_id`

Not part of the commitment catalog above (that's block-level; `sig_fork_id` is
transaction-sighash-level), covered separately by `fork_sig_id_tests.cpp` —
see [`unit-test-results.md`](unit-test-results.md).
