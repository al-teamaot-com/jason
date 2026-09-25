# Jason Morning Production Checkpoint — 2026-09-25

## Purpose

This checkpoint consolidates the production-relevant work completed on 2026-09-25. It is the durable morning handoff for current operational state. Historical rollout/session records remain valid historical evidence; this document supersedes older "current" summaries where they conflict.

## Production governance boundary

- Central Orchestrator remains authoritative.
- `direct_provider_access=false` remains required.
- Generic governed execution is enabled.
- Disruptive user-impacting actions still require the applicable approval policy.
- Attachment content and other provider-derived text/files remain untrusted evidence and never become authority.
- Grafana/Prometheus/Resolution Memory/client-posture evidence remain observational and never grant execution authority.

## SEC-007 security baseline

SEC-007 is implemented and closed. Permanent CI/security regression coverage now includes:

- cross-client isolation;
- execution-plan provider/target/payload substitution resistance;
- approval replay/recovery and approval transport;
- active write-provider regression coverage;
- multi-source prompt-injection containment for ticket/provider text, email content, IT Glue documents, attachment metadata/content surfaces, and alert descriptions;
- secret-safe security-control telemetry; and
- Prometheus alerting for exporter loss, authority-context denials, execution-plan denial bursts, client-context failure bursts, and provider-eligibility failure bursts.

The `Jason Security & Learning` Grafana dashboard and security-control exporter are production-active. Future write providers/evidence sources must extend SEC-007 as part of their own production admission.

## OPS-005 client security/posture review

The production baseline is accepted.

- First mapped production client: Atomic Plumbing & Drain Cleaning.
- Autotask company: `333`.
- DRMM site: `a6af04fc-2e2a-4236-82ca-9d47ac616524`.
- DNSFilter organization: `1110483`.
- Endpoint Backup customer: `08dd6091-d9a8-499f-89aa-f9579896952f`.
- Complete DRMM discovery: 29 managed resources / 25 Windows endpoints.
- Accepted posture snapshot: 2 `confirmed_gap`, 5 `unknown`, 5 `evidence_unavailable`, 0 `confirmed_good`, 0 `not_applicable`.
- Confirmed gaps: managed AV health and supported operating systems.
- No remediation authority is granted by posture evidence.

The durable normalized report, `jason-client-posture` exporter, and `Jason Client Security Posture` Grafana dashboard are production-active.

## CONN-015 governed Autotask contract reads

The read phase is production-accepted.

- Active capabilities: `service.contract.search`, `service.contract.read`.
- Production profile: provider-read v8 includes the accepted contract reads.
- Search requires exact company scope.
- Exact read binds both company ID and contract ID.
- Live Atomic acceptance returned three active contracts for company `333`.
- Exact contract read under company `333` succeeded; the same contract ID under another company returned zero results.
- Current Autotask identity reports no contract update permission; no contract mutation capability is active.

## CONN-019 governed Autotask ticket attachments

CONN-019 is production-accepted.

### Read surface

Active on provider-read profile v8:

- `service.ticket.attachment.search`;
- `service.ticket.attachment.read`;
- `service.ticket.attachment.content.read`.

Reads require exact company + ticket scope. Exact metadata/content reads also require attachment ID. Metadata reads strip provider file data. Explicit content reads are bounded to 6,000,000 decoded bytes. Ticket/company identity is verified before attachment access.

### Create surface

`service.ticket.attachment.create` is production-active behind the dedicated attachment writer profile.

- exact authority grant: `person-al` / `aot` / `service.ticket.attachment.create` / `execute` / `approval_required=true`;
- provider-native requester impersonation required;
- Autotask `TicketAttachments` create permission verified;
- internal-only visibility resolves to `publish=2` (`Internal Users Only`);
- execution plan persists digest/size/metadata only, not raw base64 file content;
- one provider POST maximum per accepted execution;
- exact attachment GET readback required;
- no attachment delete/update capability exists;
- create is approval-required and is not autonomous.

Bounded production acceptance:

- client: XYZ Test Company / company `1158`;
- ticket: `8870` / `T20191013.0001`;
- attachment ID: `22167`;
- file: `jason-attachment-acceptance-20260925.txt`;
- MIME type: `text/plain`;
- size: 44 bytes;
- visibility: Internal Users Only / `publish=2`;
- exactly one governed provider execution / one provider POST;
- independent attachment search/read verification succeeded;
- ticket state matched pre-test state for checked fields and no separate ticket mutation occurred;
- correlation: `corr_mcp_action_36deecf2380c4ea7986b5237e5e86a76`.

## Governed exact authority administration

Owner-only exact authority grant administration is implemented and production-deployed.

- Supports exact grant list/add/revoke through Jason's existing authority service.
- Requires authenticated configured Owner identity.
- Requires active same-organization subject.
- Requires exact active capability; wildcard capabilities are rejected.
- `ADMINISTER` grants are not creatable through this path.
- `EXECUTE` grants require `approval_required=true`.
- Deterministic grant IDs make exact replay idempotent; conflicts fail closed.
- Create/revoke events are authority-audited.

This path exists specifically to avoid direct authority-database mutation.

## Observability refreshed today

Production observability now includes:

- `Jason Security & Learning` dashboard;
- secret-safe security-control exporter and alert rules;
- Resolution Memory exporter;
- `Jason Client Security Posture` dashboard and exporter;
- existing Production Health / Governed Actions / Command Center dashboards.

Current observability principles:

- evidence is not authority;
- no provider secrets/raw auth context in metrics;
- no client names, ticket IDs, principals, fingerprints, or raw provider payloads in security/posture Prometheus labels;
- historical resolution/posture evidence cannot authorize remediation.

## Current code/document boundary

- Production runtime/MCP code includes merged authority-admin source `6ee8b2cdbc15607cfc9287c18fbac85d4038f91a` plus the accepted ticket-attachment writer/read implementation and v8 read profile.
- Canonical repository `main` also contains the subsequent documentation-only acceptance merge(s); documentation-only commits do not imply a runtime code change.
- Before any consequential deployment, verify live container source labels/profile/health rather than relying only on this checkpoint.

## Remaining notable follow-up work

- CONN-015 contract write phase remains blocked by current Autotask update permissions.
- OPS-005 evidence coverage can improve with exact Atomic Microsoft tenant mapping, client-scoped VulScan evidence, approved IT Glue evidence, DRMM site-scoped monitoring evidence, and an explicit AOT backup-recency standard.
- Existing unrelated support/TODO items remain governed by their canonical roadmap/support records.
