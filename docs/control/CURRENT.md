# Project Jason — Current Resume Point

**Updated:** 2026-09-27
**Production status:** Healthy governed runtime/MCP; Central Orchestrator authoritative; `direct_provider_access=false`; Project Jason is 100% constitutionally certified against J-002 as of authoritative main revision `bb0aad018ec40fb975a32b69594bdc6d6806fd1c` plus this closeout record.
**Current certification record:** `docs/governance/CONSTITUTIONAL-CERTIFICATION-2026-09-26.md`
**Morning checkpoint:** `docs/sessions/Jason-Morning-Production-Checkpoint-2026-09-25.md`

## Continuity control anchors

- **Jason fundamentals:** `docs/control/JASON-FUNDAMENTALS.md`
- **Extension construction map:** `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
- **Last durable success:** 2026-09-25 first governed autonomous provider write accepted in production; see `docs/sessions/Jason-Autonomous-Execution-Production-Acceptance-2026-09-25.md`.
- **Production/runtime boundary:** use `docs/control/AUTOMATED-CHANGE-STATE.json` / generated `AUTOMATED-CHANGE-STATE.md` for the latest reconciled validated-source and production-alignment evidence, then verify live runtime/MCP directly before consequential change. Source-validation success is not production proof.
- **Documentation continuity:** `jason-documentation-reconciliation.timer` polls successful `Validate Jason` runs on `main`, publishes generated-state PRs through Jason's authenticated GitHub identity, and merges only after the expected protected workflow set is green. Production host reconciliation also publishes production-alignment state after live runtime/MCP/release verification.
- **Source integration continuity:** trusted same-repository PRs may opt in with `Integration automation: enabled`. `pr-main-reconciliation.yml` serially incorporates current `main`, explicitly reruns the protected Validate Jason / security / Teams / conversation gates on the reconciled head, rechecks for further `main` movement, and merges only when all required checks are green. Merge conflicts, failed/missing checks, untrusted/fork PRs, drafts, and non-opted-in PRs fail closed. Source merge remains separate from production deployment/promotion.
- **Next safe actions:** constitutional certification remediation is complete. All nineteen J-002 articles are PROVEN on authoritative `main`; #175/#176 are closed; Article XIX and production-equivalent MCP certification are proven; ADR-011 is canonical. Resume normal roadmap work, but re-run constitutional certification after any material constitutional architecture, authority, identity, provider-boundary, recovery, or production-topology change. Certification is evidence tied to reviewed state, not a permanent waiver for future changes.

## Current production state

Project Jason's major 2026-09-25 work is production-accepted:

- **SEC-007:** permanent security regression / prompt-injection / secret-safe observability baseline implemented and closed.
- **OPS-005:** client security/posture production baseline accepted; Atomic Plumbing durable posture snapshot and Grafana posture dashboard active.
- **CONN-015 read phase:** governed Autotask contract search/read production-accepted; contract writes remain blocked by provider update permission.
- **CONN-019:** governed Autotask ticket attachment search/read/content-read and approval-required create production-accepted.
- **Authority administration:** Owner-only exact authority grant list/add/revoke production-deployed; wildcard/administer grant creation is prohibited and execute grants require approval.
- **Autonomous execution substrate:** first production autonomous provider write completed successfully under `jason-autonomy-worker`, exact JKD-001 grants, durable playbook promotion, execution-plan binding, one provider write, independent readback, and duplicate suppression. All temporary acceptance authority was revoked afterward; operational playbooks remain shadow-only until individually promoted.
- **Observability:** Security & Learning, Client Security Posture, Resolution Memory, Production Health, Governed Actions, Command Center, and the full 21-dashboard Grafana inventory are active under an evidence-not-authority model. Grafana/Prometheus now deploy from exact immutable observability release `f61ef43228d1f5072d425e11e5303ca3bb143079`; the five-minute Grafana Configuration Assurance control is production-proven, 21/21 dashboard identities/hashes and 6/6 metric dependencies pass, and the dedicated assurance exporter is healthy on port `9474`.

## Current provider-read profile

Production uses the explicit **v8** provider-read profile:

`itglue-autotask-entra-procurement-mail-contract-attachment-catalog-v8`

This preserves prior governed catalogs and adds the accepted ticket-attachment read family. Contract reads from v7 remain active. Unknown profiles/catalog drift fail closed.

## Current ticket-attachment state

Read capabilities:

- `service.ticket.attachment.search`;
- `service.ticket.attachment.read`;
- `service.ticket.attachment.content.read`.

Create capability:

- `service.ticket.attachment.create`;
- exact grant to `person-al`;
- permission `execute`;
- `approval_required=true`;
- internal-only visibility;
- one provider POST plus exact readback verification;
- no delete/update capability;
- not autonomous.

Accepted production proof: XYZ Test Company company `1158`, ticket `8870` / `T20191013.0001`, attachment `22167`, correlation `corr_mcp_action_36deecf2380c4ea7986b5237e5e86a76`. No collateral ticket mutation occurred.

## Current client posture state

Atomic Plumbing & Drain Cleaning is the first full mapped-client production posture acceptance:

- Autotask `333`;
- DRMM site `a6af04fc-2e2a-4236-82ca-9d47ac616524`;
- DNSFilter `1110483`;
- Endpoint Backup `08dd6091-d9a8-499f-89aa-f9579896952f`;
- 29 DRMM resources / 25 Windows endpoints;
- 2 confirmed gaps, 5 unknown, 5 evidence unavailable, 0 confirmed good.

The posture report/dashboard grants no remediation authority.

## Current security/authority invariants

- Central Orchestrator only.
- `direct_provider_access=false`.
- Exact requester grants.
- Provider/client isolation.
- Execute grants that require approval remain approval-gated.
- External/provider text and file content are untrusted evidence.
- Execution-plan binding remains fail-closed on provider/target/payload drift.
- Security/posture/Resolution Memory/Grafana evidence never grants authority.

## Current observability

Production includes secret-safe exporters/dashboards for:

- production health;
- governed actions;
- security controls and Security & Learning;
- Resolution Memory;
- client security posture;
- usage/attribution/roadmap/command-center views.

Security/posture metrics must not contain secrets, raw auth context, client names, ticket IDs, principals, fingerprints, or raw provider payloads.

## Current source boundary

Latest machine-reconciled source-validation and production-alignment evidence is maintained in `docs/control/AUTOMATED-CHANGE-STATE.json` with generated view `docs/control/AUTOMATED-CHANGE-STATE.md`. Do not duplicate mutable runtime/source hashes here.

**Before consequential change:** use the generated state as a discovery aid, then verify live container source labels, health, activation profiles, governance status, and immutable release directly.

## Open follow-up work

- Autonomous execution testing now moves to the first real operational playbook. The execution substrate is proven, but unattended queue mutation remains disabled until an exact playbook version/capability set is separately promoted and accepted.
- Contract writes remain blocked by Autotask contract update permission.
- OPS-005 can improve evidence coverage for Microsoft tenant mapping, VulScan, IT Glue, DRMM site-scoped monitoring, and backup-recency policy.
- Other backlog/support items remain governed by `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md` and `SUPPORT.md`.

## Durable evidence

Primary autonomy acceptance: `docs/sessions/Jason-Autonomous-Execution-Production-Acceptance-2026-09-25.md`.

Morning handoff: `docs/sessions/Jason-Morning-Production-Checkpoint-2026-09-25.md`.

Historical production proofs remain under `docs/sessions/`; they should not be rewritten to look current.
