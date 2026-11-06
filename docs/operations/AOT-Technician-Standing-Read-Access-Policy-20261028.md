# Project Jason — AOT standing operational read access

**Owner instruction, October 28, 2026:** AOT technicians must be able to inspect all available *read-only* operational data, statuses, alerts, histories, health, and evidence from connected systems including Datto RMM, Datto EDR/AV, BackupIQ, Autotask, IT Glue, and Microsoft 365 without a new per-capability/per-incident permission request.

## Standing access model

The live runtime provisions one idempotent organization-level observe grant, `grant-aot-human-operational-provider-observe-v1`, using `provider-read:aot-technician-operational-v1`. The matching policy applies to an **active, authenticated human AOT organizational identity**, including JIT-enrolled Entra users; the AOT-wide internal human boundary is the currently available staff entitlement, not a claim that Entra technician-group membership has been independently verified. It is not a public, anonymous, client-user, or workload-identity grant.

The policy dynamically covers registered, active, provider-neutral, read-only capabilities advertised by approved/authorized external connector providers. A new read-only Datto EDR, Datto RMM, BackupIQ, or other approved provider capability does not need a separate JKD-001 permission grant for an AOT technician. Existing exact provider grants remain supported. The authority decision, request correlation ID and execution context remain audited.

## Nonnegotiable boundaries

- **Observe only.** No component launch, arbitrary PowerShell, AV scan initiation, quarantine/restore/delete, ticket note or ticket update, policy changes, firewall/network action, service restart, reboot, or other mutation is authorized through the standing read grant.
- **Active, verified AOT human identity only.** Service identities (including autonomous worker principals), unregistered or disabled identities, and other organizations do not inherit this broad grant. Service automation requires its own expressly governed read authority.
- **Provider and client controls remain mandatory.** Source-system permissions, trusted identity binding, tenant/customer mapping, information-release authorization, redaction, client-boundary enforcement, and source availability are not bypassed. A failed source-access check is a real provider/entitlement issue, not grounds to weaken these protections.
- **Approved providers and registered reads only.** Disabled providers, unregistered capabilities, or a capability not explicitly registered as `read_only=true` and `provider_neutral=true` do not match. Remotely executed PowerShell—even when deterministic read-only—is excluded from this passive information entitlement.
- **No case-by-case approval for information retrieval.** If a supported AOT technician read is denied solely because of a missing organization-specific JKD-001 read grant, that is a Jason configuration defect requiring correction, not a reason to ask the technician for the same access again.

## Acceptance

Tests must verify EDR detections and quarantine, DRMM endpoint state, backup assets and alerts, and preserve denied write, unknown, cross-organization, service-identity, disabled-user, and cross-client cases. The protected release process and freeze policy remain unchanged; this documentation and source change do not authorize an unreviewed production deployment. Post-deployment verification must use real MCP requests for endpoint security, DRMM, and backup reads and compare pre-/post-release authority outcomes.
