# Jason Ticket Split Runtime Contract

## 1. Section Goal

**Goal:** Provide one reusable governed runtime primitive that converts one source service ticket containing multiple independently actionable targets into one verified child ticket per target without weakening any playbook's authority boundary.

**Success means:**
- each child represents exactly one verified target;
- each child is created through `service.ticket.create` under the caller's exact approved scope;
- retries do not duplicate previously verified children;
- source/child lineage is durable and visible;
- the source is not completed until every requested child has provider readback;
- the primitive grants no authority by itself.

## 2. Trigger

This runtime primitive has no autonomous trigger of its own. A playbook or governed workflow invokes it only after that caller has independently determined that a source ticket contains two or more independently actionable targets.

## 3. Scope and Boundaries

### In Scope
- provider-neutral composite ticket creation;
- deterministic per-target split keys;
- one CI/object binding per child;
- durable idempotency state;
- source-ticket lineage markers;
- provider readback verification for every created child.

### Out of Scope
- deciding whether a source should be split;
- resolving target identity;
- granting `service.ticket.create` authority;
- weakening client/tenant isolation;
- disruptive endpoint actions;
- completing the source before all children are verified.

Preserve `direct_provider_access=false`, Central Orchestrator authority, exact requester/playbook grants, provider/client isolation, and audit.

## 4. Initial Identification

The calling workflow must provide:
1. exact source ticket ID and ticket number;
2. exact company/client;
3. two or more unique target keys;
4. exactly one verified CI/object per target;
5. desired child queue and priority;
6. bounded child title/description content.

If any target is ambiguous, do not partially invent or guess a target identity.

## 5. Expected State

After a successful split:
- one durable child exists per requested target;
- every child has the intended company, title, queue, priority, and single CI/object;
- every child contains the source ticket number and deterministic split marker;
- the local split ledger maps `source_ticket_id + target_key -> child_ticket_id`;
- the source workflow may then document the split and perform its own terminal disposition.

## 6. State Model

`requested -> creating_children -> verifying_children -> split_complete`

Per target:
`uncreated -> created_verified`

On failure:
`creating_children -> retryable_failure`

Verified children remain persisted and are reused on retry. A retry must never recreate a child already recorded for the same source ticket and target key.

## 7. Diagnostic Workflow

Before each child create:
- check the durable split ledger for an existing source/target mapping;
- if present, reuse it;
- otherwise create exactly one child through `service.ticket.create`;
- require provider post-create readback;
- persist the mapping only after verified readback.

## 8. Decision Gates

Before invocation:
- at least two unique targets;
- all targets independently identified;
- caller has exact `service.ticket.create` authority;
- source ticket and company are known;
- child queue/priority are bounded.

Before source completion:
- child count equals requested target count;
- every child has durable verified identity;
- no target remains unresolved.

## 9. Remediation / Mutation Authority

The primitive performs service-ticket creation only. It does not authorize itself.

**Authority classification:** modifying, non-disruptive PSA action.

The caller must supply an approved workflow scope containing `service.ticket.create`. Ticket note/update actions remain separately governed by the caller.

## 10. Retry and Recheck Rules

- retries reuse persisted verified children;
- a create failure stops the current split attempt;
- successful earlier children are retained;
- retry resumes with the first unverified target;
- duplicate target keys in one request fail closed.

## 11. Dependencies

- active governed `service.ticket.create` provider;
- provider readback verification;
- durable SQLite split ledger;
- calling workflow's identity-resolution logic.

## 12. Documentation

Each child description includes:
- source ticket number;
- target key;
- deterministic split marker;
- caller-supplied target-specific evidence.

The source workflow should record the verified child IDs before completing the source.

## 13. Failure and Escalation Handling

Fail closed when:
- target identity is ambiguous;
- ticket-create authority is absent;
- provider create fails;
- provider readback fails;
- durable split state conflicts with a different child ID.

The calling workflow decides whether that failure waits, retries, or hands off to Human Review.

## 14. Verification

A child is successful only when the ticket-create provider returns a durable ticket ID and its post-create readback succeeds.

## 15. Completion

The split primitive returns complete only when every requested target has a verified child ticket.

## 16. Required Capabilities

- `service.ticket.create` under the caller's approved scope.

The calling workflow generally also needs ticket read/update/note capabilities, but those are not granted by the split primitive.

## 17. Acceptance Test

1. source with two verified targets creates two children;
2. both children receive distinct CI bindings;
3. both contain source lineage and deterministic markers;
4. a second identical invocation creates zero new tickets;
5. provider readback failure creates no durable split mapping;
6. one-target request fails closed;
7. missing caller authority prevents any child creation.

## 18. Section Goal Closure

Complete when runtime tests pass, at least one governed playbook consumes the primitive successfully, live readback proves child creation, duplicate suppression is demonstrated, and any limitations are recorded.
