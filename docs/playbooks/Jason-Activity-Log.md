# Jason Playbook: Managed Activity Log

**Version:** 1.0.0  
**Status:** Production scope; exact durable owner promotion required  
**Mode:** Internal documentation only

## 1. Section Goal

**Goal:** Keep one readable, chronological Jason work-history note on every ticket that enters Jason's persisted operational-work state, without producing a separate Autotask note for every check or unchanged poll.

**Success means:**
- meaningful Jason state changes appear in `Jason Activity`;
- unchanged consecutive state/reason pairs are suppressed;
- existing history is append-only;
- long histories roll to `Jason Activity 2`, `Jason Activity 3`, and so on;
- only Jason-owned internal notes can be updated.

## 2. Trigger

A ticket has persisted Jason operational activity and at least one meaningful state/reason transition.

## 3. Scope and Boundaries

### In Scope
- Jason operational-work state transitions already persisted locally;
- creation/update of `Jason Activity` internal notes;
- deterministic rollover when a note body reaches the bounded size.

### Out of Scope
- client communications;
- technician/client/workflow note modification;
- ticket field mutation;
- remediation;
- disruptive actions.

## 4. Initial Identification

1. Resolve exact ticket ID from persisted operational work.
2. Read that ticket's existing notes.
3. Identify at most one exact note for each managed title.
4. Require the governed note-update boundary to verify creator identity, internal visibility, and note ID.

## 5. Expected State

The ticket contains a compact chronological activity history reflecting meaningful Jason state transitions, with no duplicate entries for unchanged polling.

## 6. State Model

`activity_detected -> rendered -> current | created | appended | rollover_created | blocked`

The source of truth is `autonomy_ticket_activity`; Autotask is the technician-readable projection.

## 7. Diagnostic Workflow

### Step 1: Read persisted activity
Read ordered activity rows for the exact ticket.

### Step 2: Suppress noise
Remove consecutive rows with identical phase and reason.

### Step 3: Render deterministic chunks
Render stable timestamp/state/result entries and greedily chunk from the beginning. Existing chunk boundaries never move when new rows are appended.

### Step 4: Reconcile notes
- absent chunk -> create internal note;
- exact body -> no write;
- longer body -> append-only managed update;
- ownership/identity mismatch -> fail closed.

## 8. Decision Gates

- persisted operational work exists;
- exact durable `jason_activity_log@1.0.0` promotion exists;
- only internal-note create/update capabilities are allowed;
- note update passes exact Jason ownership verification;
- revised Activity body preserves the entire prior body as a prefix.

## 9. Remediation

Not applicable. Documentation only.

Allowed mutations:
- `service.ticket.note.create`
- `service.ticket.note.update`

## 10. Retry Policy

No provider mutation retry inside one execution plan. Later normal worker cycles may reconcile again after authoritative reread.

## 11. Periodic Rechecks

Normal worker scans reevaluate activity. Unchanged activity generates no Autotask write.

## 12. Aging / Stale Condition

Historical activity remains readable after terminal ticket state. No endless polling entries are appended.

## 13. Dependency Handling

If note search, ownership verification, provider authorization, or readback is unavailable, skip the documentation mutation and audit the failure. Do not block technical remediation solely because Activity projection failed.

## 14. Documentation Requirements

Entry format contains:
- timestamp;
- human-readable activity label;
- result/reason;
- persisted Jason state.

The full before/after note bodies and SHA-256 values are captured in Jason's managed-note revision audit for every update.

## 15. Failure Handling

Fail closed on:
- duplicate managed-note titles;
- non-Jason creator;
- client-visible note metadata;
- attempt to replace rather than append Activity history;
- provider mutation/readback mismatch.

## 16. Escalation Criteria

Repeated projection failures are a Jason support condition; they do not authorize altering unrelated ticket data.

## 17. Verification

Authoritative Autotask readback must prove exact body, note ID, internal visibility, title, and Jason creator attribution.

## 18. Completion Criteria

The latest meaningful persisted activity is represented in the deterministic managed-note projection, or the existing projection is already current.

## 19. Final Resolution Note

Not applicable. The Activity note itself is the chronological technical record.

## 20. Required Capabilities

- `service.ticket.notes.search`
- `service.ticket.note.create`
- `service.ticket.note.update`
- persisted `autonomy_ticket_activity` state

## 21. Acceptance Test

Prove:
1. first meaningful activity creates `Jason Activity`;
2. unchanged repeated state creates no write;
3. a changed state appends to the same note;
4. attempted overwrite is rejected;
5. technician/client/workflow note cannot be updated;
6. internal visibility is preserved;
7. rollover creates `Jason Activity 2` without changing prior chunk;
8. full revision audit and SHA-256 evidence exist;
9. post-write readback verifies exact result.

## 22. Section Goal Closure

Close after source tests, protected CI, exact durable owner promotion, production deployment, and a controlled live work-ticket verification.

## 23. Autonomous Execution Eligibility and Owner Review

Production nomination: `autonomy.activation=autonomous`.

Exact promoted scope:
- playbook: `jason_activity_log@1.0.0`
- policy: `playbook-autonomy:jason_activity_log`
- capabilities: `service.ticket.note.create`, `service.ticket.note.update`

Any material expansion beyond Jason-owned internal documentation requires new owner review.
