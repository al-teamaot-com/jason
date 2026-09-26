# Project Jason Constitutional Certification Review — 2026-09-26

**Status:** Initial certification audit — NOT YET 100% CERTIFIED  
**Owner:** Jason Architecture Authority  
**Authority:** `docs/foundation/J-002-Constitution.md`; `docs/standards/J-404-Documentation-Governance-and-Continuity.md`; `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md`  
**Scope:** Authoritative `origin/main` at `60db7bd2a0ab74f8b4a4d84b09b15c7deda9984c`, current live Jason MCP boundary, current production governance records, and open governance exceptions as of 2026-09-26.

## Certification vocabulary

- **PROVEN** — current source/tests plus production or durable evidence support the requirement.
- **PARTIAL** — substantially implemented but a required proof, control, or documentation element is incomplete.
- **EXCEPTION** — a deliberate temporary deviation exists with compensating controls; it blocks 100% certification until retired or fully governed.
- **FAIL** — current behavior or state contradicts a controlling requirement.
- **STALE TRACKING** — an open record describes a defect that current durable evidence appears to have corrected; tracking must be reconciled.
- **NOT MECHANICALLY CERTIFIABLE** — principle requires architecture/human review rather than a binary unit-test result.

## Executive result

Project Jason is operating under its constitutional model, but it is **not yet 100% constitutionally certified**. No current evidence reviewed in this audit shows an active deliberate bypass of Central Orchestrator authority, direct provider access from MCP, autonomous user-disruptive action without approval, cross-client release, secret disclosure, or provider write outside the governed mutation path. The live MCP reports `governed_execution=central-orchestrator` and `direct_provider_access=false`.

Certification is blocked by unresolved governance debt and proof gaps, principally:

1. temporary Jason-managed requester-authorization compatibility modes for Autotask and IT Glue remain active exceptions pending retirement, although they are now formally governed under J-405 with review due 2026-10-15;
2. `CURRENT.md` was stale before this audit and is corrected by the certification workstream;
3. full-host reboot acceptance for the OpenBao recovery control remains intentionally unperformed because reboot is disruptive, although bounded recovery evidence now exists and the original P0 #56 has been reconciled/closed;
5. MCP-server tests still need a production-equivalent certification runner because the host venv lacks MCP runtime dependencies;
6. several constitutional principles (mission, simplicity, stewardship quality) require periodic architectural/human review and cannot honestly be certified by unit tests alone.

## Constitutional article matrix

| Article | Result | Current evidence / rationale |
|---|---|---|
| I — Mission First | NOT MECHANICALLY CERTIFIABLE | Mission is clearly represented in canonical foundation material and current work prioritizes dependable/secure client service. Requires owner/architecture review rather than a binary test. |
| II — Human Governance | PROVEN | Exact grants, approval-required execution, owner-only authority administration, fail-closed denial, and the prohibition on autonomous disruptive actions are implemented and repeatedly accepted in production. |
| III — Architecture Before Implementation | PARTIAL | Canonical architecture/ADRs and construction guidance exist. Most current work is architecture-led, but certification must continue to verify new implementation branches are preceded by or tied to authoritative design records. |
| IV — Independence and Capability Abstraction | PROVEN | Provider-neutral capability/resource registries, provider resolution, and replaceable connector boundaries are current architecture. Live MCP does not expose unrestricted provider access. |
| V — Integration Before Innovation | PARTIAL | Strongly represented in ADRs/JIS and recent decisions, but not every historical/custom component has independently verified purpose/review/retirement evidence in this audit. |
| VI — Separation of Responsibilities | PROVEN | Central Orchestrator is the live governed execution coordinator; direct provider access is false; agent/provider/interface boundaries are documented and tested. |
| VII — Knowledge as an Asset | PROVEN | Governed docs, decision memory, playbooks, System Registry, session proof records, and documentation-control standards are established. |
| VIII — Explainability | PROVEN | Governed actions retain authority/evidence/correlation reasons and operational outcomes are reviewable. This does not require disclosure of private model chain-of-thought. |
| IX — Auditability | PROVEN | Significant reads/writes/approvals carry correlation/audit evidence; mutation readback and execution-plan evidence are established. |
| X — Appropriate Abstraction | PROVEN | Foundation/architecture records remain provider-neutral while implementation/provider detail is separated into engineering, component, provider, and runbook records. |
| XI — Stewardship | PARTIAL | Stewardship is defined and dependency/roadmap tracking exists, but this audit has not proven a complete recurring stewardship review cadence for every important dependency. |
| XII — Institutional Memory | PARTIAL | Durable ADR/session/runbook records are strong. `CURRENT.md` had become stale by one day while major work advanced; this is a documentation-control defect being corrected in this workstream. |
| XIII — Simplicity | NOT MECHANICALLY CERTIFIABLE | Architecture increasingly removes duplicated reasoning and favors reusable capability boundaries, but simplicity is a design-review judgment and requires continuing stewardship. |
| XIV — Expandability | PROVEN | New providers/capabilities have been added through registries/adapters without redefining Jason identity or core governance. |
| XV — Continuity and Resilience | PARTIAL / EXCEPTION | OpenBao recovery now has verified sealed→unsealed proof, bootstrap retirement, protected recovery control, and an owner-approved single-host pilot exception. Full-host reboot acceptance remains pending explicit disruptive approval; long-term multi-host/KMS or split-custody design remains hardening work. |
| XVI — Modularity and Reversibility | PROVEN | Provider/capability boundaries, lifecycle states, rollback images/checkpoints, profile gating, and fail-closed activation provide strong reversibility evidence. |
| XVII — Living Documentation | PARTIAL | Documentation control plane and J-404 are strong, but `CURRENT.md` staleness demonstrates the process is not yet perfect. This review updates the resume point and creates a formal certification record. |
| XVIII — Trust | PARTIAL | Current fail-closed behavior, approval boundaries, auditability, and no-bypass decisions support trust; unresolved temporary exceptions prevent a 100% trust certification. |
| XIX — Authoritative Operational State | **PROVEN** | Article XIX was remediated during this audit. The System Registry now contains 233 entities and the deterministic live completeness gate reports zero missing active capabilities, providers, non-ephemeral live components, active Microsoft→Jason identity bindings, and mounted OpenBao credential profiles; no stale operational containers were detected. The live governance path is explicitly registered, including JKD-001 through JKD-007, client-boundary enforcement, information-release authorization, execution-plan binding, Central Orchestrator, durable orchestration event store, and governed execution ledger. Nine bounded host probes verify successfully and the full System Registry/governance regression battery passes. Durable evidence: `docs/sessions/System-Registry-Completeness-Result-2026-09-26.json` and `docs/sessions/System-Registry-Verification-Final-2026-09-26.json`. P0 #378 resolved. |

## Subordinate platform-integrity review (J-405)

### Proven controls

- Central Orchestrator remains the governed execution coordinator.
- Live MCP reports `direct_provider_access=false`.
- Exact authority grants and approval-required execution are enforced.
- Provider writes remain separately credentialed/profile-gated and readback-verified where applicable.
- Execution-plan target/provider/payload drift fails closed.
- Cross-client and information-release boundaries have deterministic tests.
- Secret values are excluded from ordinary documentation/evidence by policy and current runbooks.
- Direct datastore/provider bypasses were explicitly refused during current engineering work rather than used to escape governance.

### Current exceptions / partials

#### Autotask requester authorization — GitHub #175

Current production reads use temporary `JASON_AUTOTASK_REQUESTER_AUTH_MODE=jason_managed` because provider-native `ImpersonationResourceId` reads hit an Autotask HTTP 500. Compensating controls preserve authenticated human binding, JKD-001 authority, validated authority context, observe-only mode, Central Orchestrator execution, information-release authorization, sensitivity handling, and separate write governance.

**Certification:** EXCEPTION. The control remains temporary, governed, and fail-closed. A formal J-405 exception record now exists at `docs/governance/EXCEPTION-AUTOTASK-REQUESTER-AUTH-2026-09-26.md` with approving authority, scope, compensating controls, evidence, retirement criteria, and mandatory review no later than 2026-10-15. The exception continues to block a 100% certification until retired or replaced by a stronger accepted requester-authorization design.

#### IT Glue requester authorization — GitHub #176

IT Glue uses a parallel temporary Jason-managed requester-authorization model with provider/source-native restriction semantics preserved where available.

**Certification:** EXCEPTION. Security controls remain intact and a formal J-405 exception record now exists at `docs/governance/EXCEPTION-ITGLUE-REQUESTER-AUTH-2026-09-26.md` with approving authority, scope, compensating controls, evidence, retirement criteria, and mandatory review no later than 2026-10-15. The active exception still blocks 100% certification until retired or replaced.

## Stale-tracking review

### GitHub #56 — OpenBao recovery readiness

The issue was opened when recovery custody, bootstrap disposition, and recovery-test evidence were missing. Current canonical recovery documentation now records:

- Shamir 3-of-5 recovery structure without secret values;
- protected root-only initialization artifact and verified fingerprint;
- revoked bootstrap credential and removed temporary bootstrap files;
- provider-specific AppRole runtime identities;
- successful 2026-09-24 sealed→unsealed recovery using protected shares without disclosure;
- successful boot-recovery service acceptance;
- explicit owner-approved single-host pilot exception;
- fail-closed recovery conditions and evidence references.

**Certification:** RESOLVED / ISSUE CLOSED. The original P0 condition is corrected for the approved single-host pilot. Focused recovery-readiness and production-closeout tests passed 14/14 during this audit, including missing-field/custody denial and no-bypass behavior. GitHub #56 was reconciled with current evidence and closed on 2026-09-26. The remaining full-host reboot test is separately gated because reboot is user-disruptive, and long-term multi-host/KMS or split-custody hardening remains documented.

### GitHub #165 — governance restoration checklist

The issue still shows all eight restoration controls unchecked, but current architecture/tests/production evidence demonstrate that many are now implemented: authenticated ingress, identity/organization authorization, capability authorization, target invariance, approval controls, evidence-before-assertion, deterministic execution-plan validation, and outbound/audit controls all have later implementation evidence.

**Certification:** RESOLVED / ISSUE CLOSED. The eight restoration gates were re-audited against current architecture and a combined focused suite covering authenticated ingress, identity/organization binding, capability/target authority, approval resume, execution-plan binding, evidence support, approval audit persistence, and return-path correlation. The suite passed completely, and later production proof/ADRs supersede the historical working-first checkpoint. GitHub #165 was reconciled and closed on 2026-09-26.

## Verification performed in this audit

### Live runtime evidence

Jason MCP reported:

- service status: `ok`;
- mode: `governed-read-plus-actions`;
- governed execution: `central-orchestrator`;
- generic execution tool: enabled;
- direct provider access: `false`;
- write authority: exact Jason grant plus server-governed approval policy.

### Focused executable governance battery

The following current-main test families were executed together and passed:

- identity and authority;
- information-release boundary;
- execution-plan binding;
- governed execution replay;
- provider-read Central Orchestrator enforcement;
- provider-read authority;
- OpenClaw/trusted ingress boundaries;
- autonomous-remediation red-team controls.

The host venv could not collect two MCP server test modules because it lacks the MCP production runtime's `PyJWT` dependency. Those modules are therefore **not counted as host-suite proof**. MCP boundary evidence in this audit uses the live MCP status plus previously accepted production/runtime image evidence; a future certification runner should execute the MCP tests inside the production-equivalent MCP image so dependency parity is guaranteed.

## Immediate remediation plan

1. Continue provider-native/delegated requester-authorization investigation and retire the formally governed Autotask #175 and IT Glue #176 compatibility exceptions when safe; mandatory exception review is due no later than 2026-10-15.
2. Add a production-equivalent constitutional test runner that includes MCP dependencies and produces a durable certification artifact tied to a source revision.
3. Review the remaining PARTIAL / NOT MECHANICALLY CERTIFIABLE constitutional articles with explicit architecture/owner evidence rather than pretending unit tests can settle them.
4. Keep `docs/control/CURRENT.md` synchronized whenever a material workstream changes.
5. Re-run this certification after remediation. A 100% statement may be made only when no FAIL/PARTIAL/EXCEPTION items remain and all mechanically testable controls have current evidence.

## Certification decision

**Decision: NOT 100% CERTIFIED as of 2026-09-26.**

Jason's current operational behavior is strongly constitutional and its most important authority/execution boundaries are functioning correctly. Article XIX/System Registry completeness has now been remediated and proven during this audit. The remaining blockers to a 100% certification are the still-active Autotask and IT Glue requester-authorization exceptions, production-equivalent MCP certification-runner coverage, and explicit owner/architecture review of the remaining PARTIAL / NOT MECHANICALLY CERTIFIABLE constitutional articles—not evidence that Jason is currently acting as an uncontrolled autonomous authority.
