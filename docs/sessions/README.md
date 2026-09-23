# Jason Session Records

This directory preserves daily working-session records and durable host-proof checkpoints for Project Jason.

## Purpose

Session records preserve context, reasoning, decisions, unresolved questions, host-proof outcomes, and next steps that may not yet belong in a formal foundation, architecture, governance, standard, component, roadmap, or operational document.

They are historical records, not governing authority.

When a session produces an approved decision, the authoritative result must also be incorporated into the appropriate canonical Jason document.

## Canonical resume point

`docs/control/CURRENT.md` is the human-readable resume checkpoint for the next Jason work session. Read it together with current GitHub state, the applicable ADRs/runbooks, and a fresh `tools/catch_me_up.py` host snapshot.

## Practice

For each substantive Jason working day, create a dated Markdown file using:

`YYYY-MM-DD.md`

Durable host proofs may use a descriptive dated filename when the record represents a specific operational milestone rather than the entire day.

Each record should include:

- Session scope
- Important discussion
- Decisions made
- Decisions deferred
- Risks or concerns identified
- Host/runtime facts actually proven
- Documents or repository files changed
- Open questions
- Next steps

## Current host-proof records

- `OpenClaw-Delegated-Human-Host-Proof-2026-08-08.md` — delegated-human OpenClaw/JKD-001 authority proof.
- `OpenClaw-Ed25519-Key-Rotation-Host-Proof-2026-08-09.md` — overlap-first OpenClaw signing-key rotation proof.
- `Datto-RMM-First-Live-Read-Host-Proof-2026-08-09.md` — first governed Datto RMM live-read proof.
- `IT-Glue-Datto-Host-Operational-Proof-2026-08-10.md` — physical Jason-host validation of canonical OpenBao provider AppRole runtime, IT Glue/Datto bounded live reads and discovery, Datto managed-device authority, documentation reconciliation behavior, and the regression-baseline defects discovered before the Teams approval round-trip.
- `CAP-007-Live-Pilot-Proof-2026-08-11.md` — first successful end-to-end governed CAP-007 AWS SES pilot and subsequent authenticated Teams conversational integration evidence for the approved pilot scope.

The 2026-08-10 proof is intentionally linked from the bootstrap/secrets runbook, secret-provider deployment record, convergence checklist, live convergence runbook, ADR-004, and `docs/control/CURRENT.md` so the operational facts do not depend on chat history.

## Source-of-Truth Rule

Session records provide history and context.

The Manifesto, Constitution, Canon, approved Architecture Decision Records, canonical deployment records, and other approved governing documents remain authoritative.

If a session record conflicts with an approved governing document, the approved governing document controls unless it is deliberately amended.

## Privacy and Data Handling

Do not preserve client secrets, passwords, tokens, API keys, RoleIDs, SecretIDs, OAuth bearer tokens, private keys, unseal/recovery material, regulated data, raw provider payloads, or unnecessary personally identifiable information in session records.

Sensitive operational examples should be summarized or redacted before being committed. Prefer stable external identifiers only when they are necessary for reproducible governed evidence and are approved for the record.

## Practical Limitation

ChatGPT cannot independently retrieve or export every future conversation after the fact. Session records must be created while the relevant conversation remains available. During substantive Jason sessions, ChatGPT should prepare and commit a daily summary or host-proof record when requested or when the session is being formally closed.
