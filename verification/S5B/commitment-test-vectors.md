# S5/b — Coinbase Commitment Test Vector Catalog

The coinbase-commitment mechanism (`src/consensus/fork_commitment.h`) is
scenario-agnostic and unchanged from `consensus/s1-testing` — confirmed by
direct code review before branching, and `src/test/fork_commitment_tests.cpp`
was reused unmodified. Coverage is therefore identical to
[S1's catalog](../S1/commitment-test-vectors.md); this file exists so S5/b's
annex is self-contained rather than requiring a cross-reference for its own
evidence.

## Positive vectors

| ID | Case | Test |
| --- | --- | --- |
| FC-P01 | Exact, correct commitment for the S5/b tuple (`branch_id`/`fork_no`/`scenario_id=2`) | `build_and_parse_round_trip` |

## Negative vectors

| ID | Case | Test | Status |
| --- | --- | --- | --- |
| FC-N01 | Wrong format version byte | `wrong_format_version_rejected` | Covered |
| FC-N02 | Wrong `fork_no` | `wrong_fork_no_rejected` | Covered |
| FC-N03 | Wrong `scenario_id` | `wrong_scenario_id_rejected` | Covered |
| FC-N04 | Nonzero flags byte | `nonzero_flags_rejected` | Covered |
| FC-N05 | Non-minimal push | `non_minimal_push_rejected` | Covered |
| FC-N06 | Truncated payload (27 bytes) | `truncated_payload_rejected` | Covered |
| FC-N07 | Extended payload (29 bytes) | `extended_payload_rejected` | Covered |
| FC-N08 | Correct payload followed by a separate trailing script operation | — | **Not covered — inherited gap, see `open-items.md`** |
| FC-N09 | Correct script, nonzero output value | `nonzero_commitment_value_rejected` | Covered |
| FC-N10 | Two identical correct outputs (duplicate) | `two_correct_commitments_still_rejected` | Covered |
| FC-N11 | One correct + one wrong-`scenario_id` output | `duplicate_commitment_rejected_even_if_one_correct` | Covered |
| FC-N12 | No commitment output at all (missing) | `missing_commitment_rejected` | Covered |
| FC-N13 | Wrong `branch_id` | `wrong_branch_id_rejected` | Covered |
| FC-N14 | One correct + one wrong-`branch_id` output | — | **Not separately asserted — inherited gap, see `open-items.md`** |

Both open items are pre-existing, inherited from S1's own unresolved
open items, not new to this scenario — carried over rather than
independently rediscovered.

## `sig_fork_id`

Covered by `fork_sig_id_tests.cpp`, reused unmodified — see
[`unit-test-results.md`](unit-test-results.md).
