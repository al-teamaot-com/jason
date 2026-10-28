# AOT routine Autotask RW pilot

**Status:** Source implemented; opt-in inactive until controlled production activation.
**Change:** Standing *human-requested* create/update/internal-note authority for Autotask tickets. No autonomous execution grant.
**Related planning baseline:** Draft PR #2112 (2026-10-28).

## What changes and what does not

- The AOT organization-wide grant uses `routine-write:aot-technician-autotask-ticket-v1`. Its capability mapping is limited to `service.ticket.create`, `service.ticket.update`, and `service.ticket.note.create`.
- The matcher requires an active authenticated AOT human identity, the exact enabled provider, active registered write capability, and established MCP authenticated-imperative behavior. An actual provider permission and trusted Autotask Resource impersonation are still required.
- The persisted grant is `EXECUTE` **with `approval_required=True`**, not a no-approval bypass: the existing MCP direct-imperative path records exact, short-lived approval evidence and binds provider execution. This removes a *second approval request* for routine direct technician instructions.
- Cross-organization/client context and non-human identities are not covered. The existing provider-native ticket company/Resource authorization and immutable execution-plan fingerprint remain authoritative.
- No new provider scopes, tenant permissions, raw Datto/PowerShell rights, high-risk capabilities, or autonomy permissions are granted. Existing read access is unchanged.

## One-setting controlled rollout

After source validation and PM authorization, set the **runtime service** environment value:

```text
JASON_AOT_ROUTINE_RW_PROFILE=autotask-ticket-v1
```

Default unset/other values: disabled. This is read during runtime composition, so a governed restart/deployment is required to apply the setting. Do not edit live environment or restart services outside the approved production-manager process. The runtime composition persists one immutable standing grant only when enabled.

## Acceptance gates

1. Compare the deployed runtime revision, MCP revision, and release manager's authorized SHA. Confirm no concurrent unrelated release is displaced.
2. Confirm exactly three approved Autotask provider operations are exposed and the JWT-bound technician maps to a permitted Autotask Resource. Confirm an unprivileged requester cannot write.
3. On a controlled XYZ Test Company ticket, use an authenticated AOT technician request to change a reversible queue or status once, then independently read it back. Require no separate owner approval, but inspect the persisted exact intent/plan approval and audit.
4. Create one internal test note on the same controlled ticket; verify attribution, contents, and deduplication. Create a test ticket only within an approved controlled test-company scope.
5. Prove negative cases: disabled/non-human/foreign principal, unauthorized provider Resource, wrong client context, unknown capability, hidden/inactive provider, invalid approval, privileged/mutating actions not on the named allowlist.
6. Confirm logs, user-visible error reason, idempotency and independent verification. Record the run and rollback state in the release manager.

## Rollback

Under PM control unset `JASON_AOT_ROUTINE_RW_PROFILE` (or set an invalid value), redeploy/restart via the approved mechanism, and verify new routine policy matches fail even if the durable grant remains stored. Revoke the immutable grant through approved authority administration if required. Existing explicit exact grants and read access are unaffected.

## Not yet included

IT Glue RW, Datto RMM mutation defaults and Entra/AD standard user onboarding require independently proven connectors and capability-specific acceptance. Do not infer they are active from this Autotask slice.
