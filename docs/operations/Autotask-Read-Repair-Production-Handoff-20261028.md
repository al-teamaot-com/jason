# Autotask Read Repair — Production Handoff (candidate, NOT approved)

## Source and tested scope
PR #2110, branch `feature/autotask-read-repair-preprod-20261028`.
Candidate source pin before this documentation change: `239f110e4256f7bf1f58c0edaece231d5f681450`.
GitHub: nine CI workflows passed at that pin; isolated source test suite: 78 passed (contract context, provider read foundation, time-entry simulated requester authorization, company search, information authorization, credential isolation).

## Change behavior
- Partial company-name search is translated to bounded `contains` matching; numeric IDs remain exact and cursor-bounded.
- Contract reads by trusted AOT technician require active identity binding, existing exact OBSERVE grant, an independently governed company read, and a one-minute client-scoped execution context.
- Client-bound requesters are denied when an explicit contract company selector conflicts with their client binding, before invoking the provider.
- Owner identity behavior remains compatible.
- Time-entry reads are deliberately denied pending proof that Autotask enforces per-requester impersonation. The `JASON_AUTOTASK_TIME_ENTRY_NATIVE_READ_PROVEN` flag must not be set by assumption.

## Production eligibility gates — all mandatory
1. Dedicated preproduction test identity and credential location approved; no production secret mount, root database, or provider-write credential reuse.
2. Independent preproduction runtime (isolated authority store, bind mounts and network policy) tested using the exact release artifact.
3. Live Autotask company partial-name search (`Riggins`) and pagination return authorized expected results; exact ID query remains exact.
4. Live contract search/read for authorized technician succeeds on known company, while unbound, client-bound wrong-company and disallowed identities fail closed.
5. Native TimeEntries provider-authorized requester test succeeds for a known populated ticket and denies an unauthorized requester; ticket/company row scoping verified. If unmet, the labor capability must remain disabled and be explicitly excluded from the release promise.
6. All CI workflows pass on the exact release SHA after main reconciliation and documentation changes.
7. Production Manager reviews the exact commit and container digest; explicitly approved controlled deployment with canary readback and rollback readiness. No automatic promotion.

## Rollback / blast radius
No schema migrations or record writes are part of these read changes. Revert the exact runtime/MCP images to the previously approved digests using the existing managed deployment rollback procedure if read authorization, company lookup, or service health deviates. Capture evidence without disclosing customer data or credential values.

## Current decision
**NOT PRODUCTION ELIGIBLE** until gates 1–6 are evidenced; this is a complete engineering handoff, not an approval. Production containers, configuration and databases must remain unchanged until explicitly authorized through PM.

## Final candidate integration checkpoint
Preproduction merge candidate 70086a7a4dcd518980fc95d0e8303e01f3d00106 included protected main 9ccd994659710c3251fddaa35789e790e8f826b7. The immutable candidate MCP image built and passed a network-isolated source smoke test. The current release includes unrelated mainline work in AOT routine Autotask RW, IT Glue notes RW, Entra standard-user creation, and KFS diagnostics; no such mutation capabilities are authorized by this read-only release. Concurrent PR #2125 targets governed execute and is tracked in PR #2110's Integration coordination declaration. Do not promote until exact-head CI, independent PM preproduction, and owner exact SHA approval all pass.
