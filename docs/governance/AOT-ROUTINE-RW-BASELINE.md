# AOT routine technician read/write baseline — proposed implementation
**Date:** 2026-10-28  
**Status:** Planning baseline only; **not an active grant or production deployment**  
**Source:** `docs/governance/aot-routine-rw-baseline.json`

## Decision
An authenticated, authorized AOT technician should be able to request ordinary, non-disruptive changes across a managed client without a redundant owner approval. Jason must still validate the client source of authority and the exact action. Autonomous writes require a separately approved playbook. High-risk/disruptive changes still require exact approval.

## Implementation (reuse, do not re-architect)
- Reuse JKD-001 identity and client-scoped authority, Central Orchestrator, existing J-102 exact intent/plan binding and per-capability provider adapters.
- Introduce **one standing routine-RW policy profile** selected from the existing authenticated technician principal, not a general-purpose wildcard execute grant. Expand allowed named capabilities only when independently tested.
- Classify each named capability as routine, controlled, or unsupported. Unregistered or unsupported means not executable; do not silently fall back to privileged credentials.
- Treat the JSON as an **implementation backlog and initial classification**, not as production code. Existing capability names remain authoritative; the proposed names for missing connectors are placeholders pending registration.
- Distinguish technician request from verified client authorization for onboarding, mailbox access and credential recovery. A ticket requesting an action is not automatically sufficient authority.
- Preserve idempotency, provider readback, secret-safe audit and strict no-disruption policy. Never authorize a workflow on a pattern match alone if its exact effect is unknown.

## First acceptance slices
1. Autotask: update one test ticket's status/queue, associate its device, add an internal note, and verify each change independently under a standing scoped technician grant. Check that no extra owner approval is requested for approved routine operations.
2. IT Glue: update one controlled test documentation object, with provenance, version history and readback.
3. Datto RMM: execute one explicitly approved non-disruptive diagnostic component on a controlled device; verify resulting job and no reboot/service interruption.
4. Entra/AD: create one normal test user under an authorized request in the correct tenant/source directory; check duplicate prevention, default groups and verification. Never allocate purchased licensing or privileged groups without separate authority.

## Negative acceptance tests
- Unknown or unauthenticated actor; wrong client/tenant; cross-client object; unregistered capability; unrelated provider denial; ambiguous identity; wrong action arguments; duplicate execution; unsupported verification: all deny or return a precise safe incomplete result.
- Reset MFA, grant admin role, disable user, delete backup, change security policy, restart service or reboot: exact-action approval is mandatory.
- A component cannot qualify as non-disruptive simply because it is labeled diagnostic.
- Any future autonomous promotion must bind to a tested, versioned playbook; technician-requested authority must not be reused as autonomy authority.

## Rollout boundary
No existing runtime permission is modified by this baseline. A separate, narrowly scoped implementation PR and controlled deployment is required for each provider adapter and authority-rule change. Do not bundle production deployment with creation of this baseline.

## Out of scope
Blanket API RW grants, direct provider access, bypassing approval on high-risk actions, auto-licensing purchases, authorization solely from chat text, and bulk migrations.
