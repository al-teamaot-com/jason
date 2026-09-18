# Project Jason Support List

This document is the governed support backlog for current defects, degraded capabilities, connector failures, operational blockers, and other issues that require repair or investigation.

It is intentionally separate from `TODO.md`. The TODO list tracks future ideas, enhancements, and planned capabilities; this Support List tracks things that should already work, or operational conditions that are preventing Jason from working as intended.

## How to use this document

Each item should include:

- **Issue** — what is failing or degraded.
- **Impact** — what Jason or a technician cannot reliably do because of the issue.
- **Observed behavior** — the concrete failure or evidence seen.
- **Expected behavior** — what should happen instead.
- **Scope** — affected connector, capability, provider, workflow, or environment.
- **Priority** — P0, P1, P2, or P3.
- **Status** — Open, Investigating, Mitigated, Blocked, Fixed, or Closed.
- **Owner** — person or role responsible for resolution.
- **Verification** — evidence required before the item can be closed.
- **Last observed** — most recent confirmed occurrence.

Items remain on this list until the underlying issue is fixed and the expected behavior is verified through the governed production path.

---

## Priority legend

- **P0** — production-blocking or safety-critical failure.
- **P1** — significant operational degradation affecting active work.
- **P2** — limited degradation with a usable workaround.
- **P3** — minor issue, cleanup, or low-impact defect.

---

## Open support items

### SUPPORT-CONN-001 — Autotask ticket read path failing through Jason

- **Priority:** P1
- **Status:** Open
- **Owner:** Jason Platform / Connector Support
- **Issue:** Jason's governed Autotask ticket read path is failing for an active production ticket.
- **Impact:** Jason can identify the Datto RMM alert and its associated Autotask ticket, but cannot reliably read the ticket details or ticket notes. This prevents complete autonomous troubleshooting documentation, ticket-state assessment, and normal ticket workflow processing.
- **Observed behavior:**
  - Datto RMM correctly identified critical antivirus alert `bd0882e0-8700-4985-ad89-f789b865c76e` on `AOT-50282`.
  - The alert correctly references Autotask ticket `T20260918.0005` / internal ticket ID `140629`.
  - `service.ticket.search` failed with `CAPABILITY_INVOCATION_FAILED`.
  - `service.ticket.read` failed with `CAPABILITY_INVOCATION_FAILED`.
  - `service.ticket.notes.search` was denied with `SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED` / `REQUEST_ACCESS`.
  - Governed Datto RMM reads and component execution continued to work, isolating the observed degradation to the Autotask read/authorization path rather than the entire Jason MCP service.
- **Expected behavior:** Jason should be able to search, read, and retrieve notes for authorized Autotask tickets through the governed read path, including `T20260918.0005`, without using direct provider access or bypassing governance.
- **Scope:** Jason MCP -> governed Autotask read capabilities, especially `service.ticket.search`, `service.ticket.read`, and `service.ticket.notes.search`.
- **Operational workaround:** Continue safe endpoint diagnostics through the governed Datto RMM path, but do not treat the Autotask ticket workflow as complete until ticket read access is restored.
- **Verification required for closure:**
  1. Search for `T20260918.0005` succeeds through the governed Autotask path.
  2. Read the ticket by its governed resource identifier succeeds.
  3. Ticket notes can be retrieved by an authorized Jason request.
  4. No direct-provider bypass is required.
  5. Repeat the reads in a fresh session to confirm the fix is durable.
- **Last observed:** 2026-09-18 during active antivirus troubleshooting on `AOT-50282`.

---
