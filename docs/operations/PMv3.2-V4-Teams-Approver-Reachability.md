# PMv3.2 V4 Teams production approver readiness

**Classification:** P0 operational reliability / high-risk approval control.
**Tracking:** #2376, #2015, #947, PR #2375.
**Scope:** Source-only repair; no production deployment, root-policy change,
license assignment, or generated approval. The existing Microsoft Teams
gateway and single shared ApprovalRequestService remain authoritative.

## Incident

On 2026-11-08, the V4 release policy correctly selected the *distinct*
admin Entra identity `c848022d-e13b-4457-84b0-e2f5c00dcaf6` for
`release-65e2f18b051e3dda`. The gateway returned a provider message ID,
but `al_admin@teamaot.com` could not read Teams chats: delegated Microsoft
Graph returned `403 Failed to get license information for the user`.
The regular requester identity `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`
has an existing personal bot chat, **but cannot approve this V4 action**.

The provider message ID is **not proof** the admin saw the card. The
approval expired with no signed decision. No deployment occurred.

## Single-process correction

1. **Read-only provider preflight.** The existing Teams gateway exposes an
   authenticated, read-only `/internal/proactive/approver-readiness`
   operation. It uses its pre-existing Microsoft Graph app credentials and
   verifies the exact target is an active tenant member with an
   `assignedPlans` service `TeamspaceAPI` in `Enabled` status.
   A missing Teams plan, Graph 403, missing plan data, cross-tenant identity,
   disabled admin or request authentication failure is a specific fail-closed
   response. No app installation or Teams message is performed by this check.
2. **V4 only, before durable approval creation.** The existing
   `TeamsGatewayPlaybookApprovalSender` checks the *versioned privileged
   admin binding* through the same Teams transport. The existing
   `MobileReleaseApprovalMaintenance` performs this check **before**
   creating either a normal or renewed V4 ApprovalRequest. An unreachable
   admin leaves no new pending request, no Teams send, and no expired
   one-shot approval consuming the reviewed release. A later normal
   maintenance tick can issue the offer when the same admin identity becomes
   reachable. Legacy V1/V2/V3 behavior is unchanged.
3. **Send-time defense in depth.** The existing gateway independently checks
   a `relapproval-` Adaptive Card's target immediately before bot bootstrap
   and send. A prior preflight does not become an enduring license grant.
4. **No workflow starvation.** The expected readiness denial is logged as
   `OWNER_RELEASE_APPROVER_NOT_READY` and the maintenance tick returns
   without blocking unrelated ticket, procurement or documentation work.
5. **Never bypass authority.** The code does not switch to the regular
   requester, change callback identity, create an alternative approval
   service, synthesize a receipt, extend the release TTL, reset the Owner
   freeze, issue a replacement for the already expired 2026-11-08 card, or
   grant standing release permission.

## Required live remediations, separately governed

- First verify and remediate the privileged admin's Teams entitlement:
  `al_admin@teamaot.com` must have a valid Teams-enabled Microsoft 365
  license and Teams service plan. Do not assign a new paid license, borrow
  another user's license, or change the exact privileged Entra binding
  without separately verified native Microsoft 365 authority. This
  engineering source change **does not repair Microsoft 365 licensing**.
- The previously issued approval remains expired. Use the existing
  authenticated Owner renewal procedure for the **exact** candidate/reviewed
  scope/rollback after the admin's Teams access is confirmed. No duplicate
  request may be manufactured or directly edited in SQLite.
- The release remains at the exact signed Teams approval boundary;
  production must not be deployed without the new valid signed decision and
  native release verification. The live XYZ Company UDF and client-visible
  notification are downstream acceptance, not verified by these tests.

## Test acceptance

- Graph unlicensed, Teams plan disabled, Graph 403, absent plan, wrong
  tenant/account and expired authorization deny without any send/install.
- Graph user with an enabled Teams plan passes a *read-only* preflight.
- No durable V4 approval is created for an unreachable admin; a later
  valid readiness check allows exactly one normal card.
- The approved V4 admin identity remains distinct from the regular
  requester's Entra identity. Legacy release paths remain intact.
- A provider message ID is never interpreted as human acceptance.
- All production mutation controls, approval binding, idempotency,
  rollback, Owner pause and freeze remain as-is.
