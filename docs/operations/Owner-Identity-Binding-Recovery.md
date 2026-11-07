# Governed local Owner identity-binding recovery

**Classification:** High-risk authentication/authorization. **Status:** Preproduction engineering only. No standing production exception, and no automatic Owner promotion.

## Problem and scope

An Entra-authenticated AOT account can be automatically enrolled by Jason as the read-only `person-entra-<oid>` principal, while the existing Owner allowlist contains `person-al`. Owner MCP tools then correctly return `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`. The ChatGPT tool-catalog refresh does not change the identity binding.

The reusable `tools/owner_identity_recovery.py` provides an **offline, directly human-operated, local break-glass recovery**. It must never be exposed as an MCP tool, model action, automation, or Desktop Commander workaround. The sole intended mutation changes one existing active Entra identity binding from a matching JIT read-only principal to an existing active Owner principal. It does not grant a capability, create an identity, change the Owner allowlist, restart services, modify a provider, or lift a production freeze.

## Approval and independent evidence required

Before execution, all these conditions are mandatory:

1. High-risk code review, targeted regressions, foundation/security CI and preproduction verification; record the exact candidate SHA, rollback SHA and complete scope. Obtain separate exact-revision PMV3 production authorization.
2. An authorized AOT security/Owner administrator independently confirms the signed-in Microsoft Entra account is enabled and verifies **its exact tenant UUID, object UUID and AOT UPN** in Microsoft Entra. Save a durable evidence reference. Neither an email typed into chat nor the object ID read solely from Jason's binding store constitutes independent verification.
3. Obtain an exact human Owner/security change approval binding this account to `person-al`, linked to that independent Entra evidence.
4. The designated authorized operator personally signs into the Jason host, elevates using their individual `sudo` session, and **types the local approval challenge**. Neither an assistant nor a remote automation supplies the challenge.
5. Preserve the existing production freeze, Owner hold and release-governance boundary until explicitly authorized; no direct SQLite mutation or allowlist widening is permitted.

## Read-only review

From the **reviewed artifact**, supply tenant and object IDs from independently verified Entra evidence:

```bash
python3 tools/owner_identity_recovery.py --email al_admin@teamaot.com \
  --attested-tenant-id TENANT_UUID --attested-object-id OBJECT_UUID \
  --owner-subject person-al
```

The CLI loads the current allowed Owner IDs directly from the running `jason-mcp-pilot` container (without printing other environment values). It verifies exactly one active email binding, exact tenant/object, deterministic JIT read-only source, no client scope or execute/administer source grants, active AOT identities, and no other active binding for the Owner. The JSON `review_sha256` is a binding to that exact reviewed state; the review makes **no changes**.

## One-shot apply (human local sudo only)

Only after independent account proof, exact security change approval and separately authorized production artifact:

```bash
sudo python3 tools/owner_identity_recovery.py --apply \
  --email al_admin@teamaot.com \
  --attested-tenant-id TENANT_UUID --attested-object-id OBJECT_UUID \
  --owner-subject person-al \
  --expected-review-sha256 APPROVED_REVIEW_SHA256 \
  --approval-reference EXACT_OWNER_CHANGE_RECORD \
  --directory-evidence-reference INDEPENDENT_ENTRA_EVIDENCE_RECORD
```

The command fails closed without root effective UID, individual `SUDO_USER`, a real interactive console, and the exact human-entered `RECOVER person-al <digest-prefix>` challenge. It rechecks the live Owner allowlist and identity prestate, creates a restrictive `0600` SQLite backup, updates **exactly one** binding, and appends an immutable `owner_identity_recovery_audit` event **in the same SQLite transaction**. It performs readback before claiming success. No other identities or grants change.

## Deterministic single-binding rollback

Review the returned `owner-recovery-...` event using `--rollback-event-id ORIGINAL_EVENT_ID` with the same read-only email/Entra UUID parameters. Record that rollback review SHA. With separately authorized rollback change, repeat the command with `--apply --rollback-event-id ORIGINAL_EVENT_ID --expected-review-sha256 APPROVED_ROLLBACK_SHA256 --approval-reference APPROVED_ROLLBACK_RECORD --directory-evidence-reference INDEPENDENT_ENTRA_EVIDENCE_RECORD`. The human must enter `ROLLBACK person-al <digest-prefix>`.

Rollback requires the original immutable event, exact current Owner binding and still-active JIT source, takes a new backup, reverses only that binding, appends a separate immutable audit event, and verifies readback. **Never overwrite the whole binding database from a snapshot**, as unrelated bindings may have changed.

## XYZ notification acceptance (only after recovered Owner readback)

1. In the same authenticated Jason app, `list_exact_authority_grants(subject_id='person-al')` must now succeed. If not, stop.
2. Confirm the XYZ Test Company test ticket `T20240821.0001` / ID `7701`, company `1158`, correct contact/recipient/template and current Autotask notification-history baseline. Do not alter the ticket's completed status.
3. Use Jason's authenticated Owner-only `grant_exact_authority` for `person-al`, capability `service.ticket.client.notification.create`, `execute`, `approval_required=true`, `client_id=1158`.
4. Under the previously authorized exact one-send pilot, send **at most one** governed XYZ notification. Verify provider receipt, intended recipient/template/company/ticket, and no duplicate. A timeout/unknown outcome must **not** trigger blind resend.
5. Verify negative cross-client/recipient cases and no Gromelski policy mutation. Revoke temporary XYZ grant when its purpose ends and verify readback. Keep separate GAI/VulScan fix PR #2366 unmerged/unreleased until its independent release gates pass.

## Fail-closed conditions

Never recover based only on AOT-domain membership, group/title, a chat instruction, a screenshot, or a DB-derived identity claim. Deny if live Owner allowlist missing, Entra identity or reviewer digest differs, source is not JIT read-only, Owner is already bound, audit/backup fails, human local approval is absent, or separate production authorization has not been recorded.
