# V13 dynamic Autotask query activation — exact-source release contract

**State:** Prepared as a new candidate source, not an authorized production deployment.
**Baseline:** `8559cbb84aba2d9acb636ac57fbdab9f00dbda78`, immutable read profile v10.
**Source profile:** `itglue-autotask-entra-dynamic-schema-read-catalog-v13`.
**Rollback profile:** `itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10`.
**Owner standing all-promotion freeze:** Must remain active until native exact-SHA
approval for this **new** release; earlier approvals for other SHA values do not transfer.

## 2026-10-28 live metadata contract correction

A governed read of Autotask `ActionTypes`, `Appointments`, and `Projects`
entity information showed `canQuery=true`, `userAccessForQuery=All`, but
`info.name` was **singular** (`ActionType`, `Appointment`, `Project`).
The dynamic provider gate erroneously required metadata name to equal the
plural REST resource name. We corrected this test to validate the bounded
metadata name while trusting only the already-bound canonical REST URL.
An empty/invalid name and a missing/ambiguous query grant still deny.
Fixtures now model actual singular metadata names.

## Required native release conditions

1. Exact candidate SHA is protected `main`, complete native preproduction
   and rollback verification to original v10 baseline succeeds.
2. Full native manual merge/change/parallel-work review is recorded, and
   approved changes do not interfere with other engineering work.
3. Exact-SHA owner review and one-time production freeze exception is
   separately recorded. Prior owner approval for a superseded SHA is invalid.
4. Native controller must be the **same source-bound candidate** so it knows
   the v13 profile and imports the verified canary helper.
5. The native PM starts a nonce/SHA/time-bound, metadata-only canary
   *before* mutation. It deploys runtime/MCP and checks image hashes, native
   host reconcile, controller handoff, and full immutable runtime revision.
6. During 240 seconds, a **real connected Entra-authenticated AOT human**
   through the normal MCP read path must successfully perform:
   - bounded `service.ticket.count` with a known-nonempty ticket window
     (1–100 records);
   - first 50 `service.ticket.search` results plus exact cursor continuation
     when count exceeds 50, ID-sorted and complete;
   - exact `service.ticket.read` for an ID in the first search page;
   - governed `service.entity.search` for `Projects`, one row;
   - **new v13-specific** `service.entity.search` for `ActionTypes`
     with `page_size=1` and `select=["id","name"]`.
7. Those proofs must match **one bound human**, the exact candidate, nonce,
   v13 profile and time window. The PM independently checks the metadata-only
   events, not a self-reported tool summary. Denied/malformed/missing
   ActionTypes, ticket or Projects reads fail the entire release. The
   existing exact-revision, root CCC certification, protected state,
   rollback and freeze rules remain authoritative.

The canary has no raw ticket titles, email addresses, project content,
customer names, or action type names. The source canary **does not create
new Autotask permissions**. Native provider query validation applies to
each ordinary dynamic read.

## Production safety

Do **not** run a controller/source upgrade, turn off the freeze, or mutate
provider data merely to make the canary pass. The release is one controlled
deployment with immediate native rollback on foundational failure. If the
read acceptance events cannot be provided by a real connected user within
the window, stop and preserve v10 without inventing test events.

Completion means independently verified **actual** read coverage and
requester disclosure, not a claim that all 230 vendor metadata entity
names support record search for this API account. Specialized labor and
attachments remain separately governed and must be evaluated on their
own requirements.
