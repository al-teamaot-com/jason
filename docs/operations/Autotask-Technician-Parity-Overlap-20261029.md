# Autotask technician parity — ticket-worker release overlap review

**Review date:** 2026-10-29
**Technician parity draft:** PR #2145, branch feat/autotask-technician-capability-discovery-20261029
**Reviewed protected-main baseline:** 6501a9f404f99933a49859c6c16e30effe2dfeff (PR #2144)
**Related recent releases:** #2140, #2141, #2142, #2143, #2144 (P0 #770)

## Finding: version and file reconciliation

PR #2145 was based directly on 6501a9f4 after #2144 was merged. It has no commit divergence against that protected-main baseline other than its own discovery work, and its new inventory, tests, CLI and engineering document do not replace the newly shipped ticket-worker runtime files. Do not reset or copy whole runtime trees from older branches.

The recent ticket-work repair includes worker supervision, governed unsupported-ticket evidence collection, passive endpoint audit, note-draft storage and separately promoted note/handoff gates. This overlaps in *intent* with Autotask technician operations even though the changed source paths are distinct.

## Behavior to reuse, not duplicate

- **Existing governed ticket operations:** service.ticket.note.create, service.ticket.note.update and service.ticket.update; use the existing Central Orchestrator, provider adapters, exact execution plan, requester authority and write readback, not direct Autotask HTTP.
- **Investigative internal note pilot:** playbook unsupported_readonly_triage_note v1.0.0. Source registered in implementation/autonomous_remediation/playbook_registry.json. Exact pilot tickets 143305 and 143272. Independent owner promotion, source-version/company checks, no human-owned ticket mutation, verified managed title/body, proven note ownership, durable fingerprint and retry backoff remain mandatory.
- **Human-review handoff pilot:** playbook unsupported_triage_human_review v1.0.0. Separate owner promotion, same two ticket IDs, Jason-owned queue admission, qualifying state, verified internal note, queue/status-only update, authoritative readback of both fields.
- **Production enablement is not playbook promotion.** A source registry entry marked lifecycle=production or enabled=true does not establish a live, durable scope promotion or permission to invoke writes.
- **Source-registered feature is not complete technician parity.** A note or status change is not a native merge, cannot preserve native merge-linked billing/time entries, and must not be marketed as equivalent.

## Adjustment to PR #2145

The read-only capability report accepts an explicit snapshot of the canonical source playbook registry using --workflow-registry and emits (1) source_registered_ticket_workflows, (2) existing_ticket_action_reuse and (3) a separate verification flag proving only that source was supplied. Each workflow is labeled source_registered_promotion_unverified with live_promotion_verified=false. No route, execution permission, promotion, grant or worker scheduling is created.

The report separately ingests governed read-only entityInformation evidence and technician UI observations. It distinguishes REST entity supports-operation from current API identity access; identifies native note-related route definitions (including nested endpoints); and models UI-only features without inventing REST endpoints. Ticket merge remains a candidate requiring separate provider/UI semantics and governed acceptance.

The existing #2144 source and pilot controls are verified by regression tests in test_autotask_existing_ticket_workflows.py. The new modules have no import of, mutation of, or callbacks into the live worker.

## Preproduction and release gates

1. Run the new inventory/coverage/regression suites and the #770 unsupported ticket triage tests against the exact draft head, plus broader Autotask connector/governance regressions.
2. Inspect GitHub CI on the exact commit and reconcile any new main commits before merge.
3. Obtain isolated provider-backed functional testing for write flows and any native merge/UI adapter, including tenant segregation, owner promotion, readback, billing/time conservation, duplicate suppression, and adverse authorization cases. Local tests alone do not prove this.
4. Use Production Manager's exact-SHA release impact/health/rollback workflow when a full candidate is eligible. Do not merge PR #2145 or promote a release simply because this source-only overlap review passes.
5. Preserve the production freeze, installed runtime, other worktrees, client data and the two independently promoted pilot scopes.

**Outcome of this review:** no source-file conflict with protected main 6501a9f4; real overlapping ticket behavior is now explicitly inventoried for reuse. This is a draft-only, non-executing engineering improvement; full technician parity and provider-backed preproduction acceptance remain incomplete.
