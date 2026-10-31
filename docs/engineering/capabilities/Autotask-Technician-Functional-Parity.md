# Autotask technician functional parity — engineering contract

## Standing requirement

Any action an authorized AOT technician can perform to, in, or for an Autotask ticket must be operable through Jason, subject to the same user/client scope, provider capability and approval requirements. This is a *standing product requirement*, not a sequence of one-off feature requests.

## Architecture

1. **Observe continuously:** acquire independently authenticated Autotask API documentation/metadata and technician UI feature inventories. Do not scrape arbitrary sites or infer execution rights from a feature name.
2. **Discover and diff:** compare those inventories against Jason's registered provider routes and governed capabilities, using `tools/autotask_technician_gap_report.py`. Detect new features and changes instead of assuming the existing integration covers them.
3. **Resolve the gap:** prefer the supported Autotask provider interface. If a UI-only feature has no supported API equivalent, evaluate a separately authenticated, auditable technician UI adapter. No hidden sessions, undocumented privileged API calls or blind clicking.
4. **Govern every execution:** requester identity and role, client scope, exact source/target objects, field semantics, appropriate billing/charge/time-entry handling, immutable audit, replay protection, policy decisions and approval binding precede any mutation.
5. **Validate:** prove positive and denied cases against the designated test tenant, read back provider state, check duplicate/retry behavior and unchanged baseline functionality.
6. **Promote through Production Manager:** preserve unrelated protected-main development, exact source SHA, CI results, preproduction acceptance and rollback. Production activation is separately authorized.

## Candidate workflow

A discovery finding is **never** an executable capability. It must advance through provider contract verification, security review, implementation/adapter selection, deterministic tests, provider-backed acceptance, promotion, and then requester-level authorization. New features can be *detected* without changing runtime code; no system can safely promise automatic execution of every future feature before semantics, provider support and permissions are known.

Ticket merging is an acceptance use case rather than a special-case script: verify retention of timeline, related notes, attachments, unposted/posted time and charges, billing associations, links, original/retained ticket identity, client and contact, notification semantics and rollback/conservation. Do not simulate a native merge by copying notes and closing a ticket unless explicitly approved as a documented equivalent.

## Existing ticket-worker compatibility (PR #2144)

The protected-main baseline includes ticket-worker supervised admission, read-only unsupported-ticket triage, durable note drafts and independently promoted note/handoff pilots from issue #770. Future technician actions must **reuse**, not duplicate, the existing governed Central Orchestrator capabilities and execution-plan/approval/readback infrastructure:

- `service.ticket.note.create` and `service.ticket.note.update` support a two-ticket, owner-promotion-gated internal note pilot under `unsupported_readonly_triage_note` v1.0.0.
- `service.ticket.update` supports a **separately** promoted handoff under `unsupported_triage_human_review` v1.0.0, only after verified internal note and eligible Jason-owned ticket state.
- Each existing source registry entry, even enabled and lifecycle=production, is **not proof of live owner promotion**; scope, source version, client, note ownership and provider readback must be checked independently.
- A native `Merge Into Another Ticket` operation is **not** interchangeable with note or ticket-status updates; use a verified native provider or governed technician UI adapter, retaining Autotask's original merge semantics.

The source-driven report now inventories registered ticket-action workflows with `--workflow-registry implementation/autonomous_remediation/playbook_registry.json`. That report is review-only; it never schedules work, registers new capabilities or authorizes a mutation. See `docs/operations/Autotask-Technician-Parity-Overlap-20261029.md`.

## Current implementation scope

This draft PR provides an inert capability/feature diff, a governed entityInformation evidence projector, source-registered workflow overlap inventory, report CLI, and tests. The overlapping #770 runtime has not been modified. It does **not** yet wire automated authenticated provider/UI collectors, dynamic governed provider/UI execution adapters, or native ticket merging. Those are required before claiming full technician parity or provider-backed preproduction acceptance. Production freeze remains in effect.
