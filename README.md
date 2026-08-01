# Rincoin consensus 840k transition

**This directory contains public-facing drafts for Rincoin's height-840,000 consensus
decision.** The main reason of this repository is to provide a space for public research and discussion.

- Public anchor (this repository): https://github.com/rincoin-community/consensus-840k

***The first preference is a common consensus and one chain.** The separation material exists
because agreement is uncertain and because deterministic rules are needed if incompatible
continuations remain. The introduced separation base uses an exact scheduled coinbase commitment as its only new
block-consensus branch identifier. A header-level isolation layer is documented and tested as an
inactive contingency; it is not part of the current base.*

Published 2026-08-01:
- Coordination notice: https://hackmd.io/@takologi/SyV7i13HGg


## Economic Study - Scenario Analysis

Live discussion copies, when created:

- Monetary Review Summary: (to be delivered)
- Monetary Policy and Security - Scenario Analysis: (to be delivered)
- Commitment specification: (to be delivered)
<br><br>
- Whitepaper - scenario A: (to be delivered)
- Consensus Change Specification - scenario A: (to be delivered)
<br><br>
- Whitepaper - scenario B: (to be delivered)
- Consensus Change Specification - scenario B: (to be delivered)
<br><br>
- Whitepaper - scenario C: (to be delivered)
- Consensus Change Specification - scenario C: (to be delivered)

### Publication sequence

1. [`Rincoin_Monetary_Review_Summary.pdf`](analysis/Rincoin_Monetary_Review_Summary.pdf) and 
   [`Rincoin_Monetary_Scenario_Analysis.pdf`](analysis/Rincoin_Monetary_Scenario_Analysis.pdf) — ready 
   after maintainer approval and date check (within the 7 days period from the first publication).
2. Drafts of `Whitepaper` and `Consensus Change Specification` for selected scenarios
   will follow the Scenario Analysis, will be subject to change as the discussion will progress.

## Technical Overview

Live discussion copies, when created:

- Technical overview: (to be delivered)
- Commitment specification: (to be delivered)
- Header contingency: (to be delivered)

### Publication sequence

1. [`coordination-notice.md`](coordination-notice.md) — ready after maintainer approval and date check.
2. [`technical-overview.md`](technical-overview.md) and
   [`coinbase-commitment-specification.md`](coinbase-commitment-specification.md) — technical review
   after the coordination gate permits publication.
3. [`header-isolation-contingency.md`](header-isolation-contingency.md) — the prepared inactive
   option, published with the technical study rather than as the opener.
4. [`identifier-reservation.md`](identifier-reservation.md) — used only if common consensus and
   direct identifier coordination fail.
5. Implementation artifacts, operator guidance, and readiness evidence — added as implementation
   and release gates are reached.

Protocol version, service flags, user-agent text, and header markers are not branch identity or
authentication. Block separation is not transaction replay protection.


