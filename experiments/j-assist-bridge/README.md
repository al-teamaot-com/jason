# J-Assist governed session bridge — preproduction only

This module establishes a **server-side authority contract** for a future
technician-initiated bridge. It deliberately does **not** connect the Chrome
extension or enable a network listener. It is not production-enabled.

## Existing constraints verified

The Jason runtime HTTP endpoint currently accepts signed Teams conversations
and does not attest Chrome technicians or Datto Web Remote sessions. Reusing
that endpoint for extension screenshots would not meet AOT's governance.

## Required adapter contract

1. Server-side trusted identity adapter returns the authenticated AOT technician
   and organization tenant ID. **Never accept these from browser JSON.**
2. Server-side provider-backed authorization verifies the technician's native
   Datto RMM access to the exact device immediately before each request.
3. Start requires explicit user consent, returns a short-lived session-bound
   credential, and binds one technician, tenant, and Datto device.
4. Stop, expiration, permission loss and changed session immediately revoke access.
5. Only lifecycle metadata is accepted in this initial module. **No screenshot,
   raw PowerShell output, browser token or page content may be transmitted yet.**
6. Before content enablement, implement and independently accept private network
   TLS ingress, authentication, authenticated origin binding, screenshot/text
   redaction, data minimization, audit retention, rate limits and proof that
   another technician cannot read the session.
7. No command execution or endpoint mutation is part of J-Assist v1.

## Validation

Run: `python3 -m unittest discover -s experiments/j-assist-bridge/tests -v`

Unit tests use synthetic trusted identities and synthetic provider authorizers.
They are not live provider-backed acceptance or proof of real identity binding.
The browser extension remains entirely local-preview only.

## JKD-001 integration (preproduction)

`jkd_authority.make_jkd_datto_authorizer` calls Jason's existing
`IdentityAuthorityService.evaluate` on every session request and requires an
explicit `j_assist.session.observe` OBSERVE grant, plus a separately injected
provider-backed **native Datto device-access** check. Neither an AOT standing
read grant nor a browser-declared identity is sufficient. Denials and revocations
fail closed. No new grant, new role or token is provisioned by this code.

The native Datto role/permission query and Microsoft identity attestation are
still missing production adapters. Tests use real JKD service objects but
synthetic identities and provider permissions. These tests do not prove an
actual Datto technician's access.

## Shared-session architecture reconciliation (2026-11-06)

The existing draft shared-session foundation is tracked at PR #1465,
branch `feature/shared-session-foundation-20261015` and documented in
`docs/architecture/Shared-Governed-Interactive-Sessions.md` on that
branch. J-Assist must integrate with the shared, provider-neutral
session lifecycle, events and audit model; the `SessionGate` here is
an **isolated security boundary prototype**, not a second competing
production session registry. Production implementation should adapt
the already-reviewed foundation rather than promoting both ledgers
or issuing independent grants.

Datto Web Remote is browser/WebRTC driven. No supported third-party API
for joining or controlling its live terminal was established in the
existing foundation. Graphical **visible-tab snapshots** are different
from programmable WebRTC control and do not imply the latter is available.

### Next acceptance milestones

1. Bring the session authority into the provider-neutral shared-session
   architecture, preserving its durable evidence, revocation and policy
   boundaries; reject unreviewed overlapping contracts.
2. Implement trusted Microsoft/AOT human identity binding and verify each
   technician's native Datto role, tenant and exact device access.
3. Implement a reviewed TLS-protected, authenticated, server-side session
   ingress with explicit consent and stop; deny traffic before those checks.
4. Introduce bounded *opt-in* single-frame sharing and redact/suppress
   sensitive material. Full-screen continuous streaming must remain off
   until explicit handling, review, retention and audit are accepted.
5. Pass two-technician and cross-client isolation tests, race/replay
   testing, production health requirements and explicit release authority.

The current deliverables prove only local browser capture and offline
contract tests, not technician-to-Jason data delivery or vision inference.
