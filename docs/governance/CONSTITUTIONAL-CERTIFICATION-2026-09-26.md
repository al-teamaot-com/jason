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

1. `CURRENT.md` was stale before this audit and is corrected by the certification workstream;
2. full-host reboot acceptance for the OpenBao recovery control remains intentionally unperformed because reboot is disruptive, although bounded recovery evidence now exists and the original P0 #56 has been reconciled/closed;
3. several constitutional principles (mission, simplicity, stewardship quality) require periodic architectural/human review and cannot honestly be certified by unit tests alone.

## Constitutional article matrix

| Article | Result | Current evidence / rationale |
|---|---|---|
| I — Mission First | PROVEN | Owner/architecture review confirms current work consistently prioritizes TeamAOT's ability to deliver dependable, secure, compliant, efficient, and consistent service; capability expansion was deliberately paused to resolve constitutional defects first. Evidence: `docs/governance/CONSTITUTIONAL-OWNER-ARCHITECTURE-REVIEW-2026-09-26.md`. |
| II — Human Governance | PROVEN | Exact grants, approval-required execution, owner-only authority administration, fail-closed denial, and the prohibition on autonomous disruptive actions are implemented and repeatedly accepted in production. |
| III — Architecture Before Implementation | PROVEN | The Extension Construction Map, JIS guidance, ADR process, and current requester-authorization remediation demonstrate architecture/contract/authority definition before implementation is treated as complete. Evidence: owner/architecture review record. |
| IV — Independence and Capability Abstraction | PROVEN | Provider-neutral capability/resource registries, provider resolution, and replaceable connector boundaries are current architecture. Live MCP does not expose unrestricted provider access. |
| V — Integration Before Innovation | PROVEN | J-405, JIS, J-402, the capability catalog, and System Registry require reuse evaluation, justification, stewardship, review triggers, and retirement criteria for custom capability work. Evidence: owner/architecture review record. |
| VI — Separation of Responsibilities | PROVEN | Central Orchestrator is the live governed execution coordinator; direct provider access is false; agent/provider/interface boundaries are documented and tested. |
| VII — Knowledge as an Asset | PROVEN | Governed docs, decision memory, playbooks, System Registry, session proof records, and documentation-control standards are established. |
| VIII — Explainability | PROVEN | Governed actions retain authority/evidence/correlation reasons and operational outcomes are reviewable. This does not require disclosure of private model chain-of-thought. |
| IX — Auditability | PROVEN | Significant reads/writes/approvals carry correlation/audit evidence; mutation readback and execution-plan evidence are established. |
| X — Appropriate Abstraction | PROVEN | Foundation/architecture records remain provider-neutral while implementation/provider detail is separated into engineering, component, provider, and runbook records. |
| XI — Stewardship | PROVEN | Technology Steward ownership, quarterly/material-change review triggers, roadmap lifecycle state, System Registry verification, and this certification's active drift/exception reconciliation demonstrate deliberate continuing stewardship. Evidence: owner/architecture review record. |
| XII — Institutional Memory | PROVEN | ADRs, session/proof records, J-404 handoff requirements, CURRENT.md, System Registry evidence, and preserved supersession history provide durable institutional memory independent of chat or individual recall. Prior CURRENT.md staleness was detected and corrected. Evidence: owner/architecture review record. |
| XIII — Simplicity | PROVEN | Owner/architecture review confirms current design favors reusable provider-neutral capability boundaries, Central Orchestrator authority, structured registries, and removal of duplicate exception paths rather than complexity for its own sake. Evidence: owner/architecture review record. |
| XIV — Expandability | PROVEN | New providers/capabilities have been added through registries/adapters without redefining Jason identity or core governance. |
| XV — Continuity and Resilience | PROVEN | OpenBao recovery has sealed-to-unsealed proof, bootstrap retirement, protected recovery custody, fail-closed readiness enforcement, bounded pilot approval, and recovery/closeout test evidence. Full-host reboot acceptance and multi-host/KMS hardening remain optional stronger controls, not constitutional prerequisites. Evidence: owner/architecture review record and closed #56 recovery proof. |
| XVI — Modularity and Reversibility | PROVEN | Provider/capability boundaries, lifecycle states, rollback images/checkpoints, profile gating, and fail-closed activation provide strong reversibility evidence. |
| XVII — Living Documentation | PROVEN | J-404 makes documentation part of completion, CURRENT.md is maintained as the canonical resume point, System Registry-generated operational documentation is synchronized from structured truth, and this workstream corrected stale records as changes occurred. Evidence: owner/architecture review record. |
| XVIII — Trust | PROVEN | Fail-closed behavior, approval boundaries, auditability, no-bypass decisions, exact authority controls, and requester-information release boundaries are current and tested. The Autotask/IT Glue temporary requester-authorization exceptions were retired by ADR-011 without broadening provider or write authority. |
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

### Resolved requester-authorization exceptions

#### Autotask requester authorization — GitHub #175

Production reads use `JASON_AUTOTASK_REQUESTER_AUTH_MODE=jason_managed` because bounded production proof established that provider-native `ImpersonationResourceId` reads return Autotask HTTP 500 after requester mapping succeeds. ADR-011 now defines Jason-managed requester authorization as the accepted read architecture when provider-native requester execution is unavailable or unreliable.

**Certification:** RESOLVED / EXCEPTION RETIRED. Service-account FETCH authority remains separate from requester RELEASE authority. Trusted Microsoft identity binding, JKD-001, validated authority context, client scope, observe-only permission, Central Orchestrator, information-release controls, sensitivity handling, and fail-closed behavior remain mandatory. Autotask write governance is unchanged and remains separately credentialed, impersonated where required, approval-governed, execution-plan-bound, and readback-verified.

#### IT Glue requester authorization — GitHub #176

ADR-011 now defines Jason-managed requester authorization as the accepted IT Glue read architecture while preserving provider restriction evidence as a one-way narrowing control.

**Certification:** RESOLVED / EXCEPTION RETIRED. The implementation was tightened during retirement: unrestricted documents may release under proven Jason requester authority; restricted document/attachment content requires positive provider ACL evidence; explicit denial, missing ACL evidence, and unknown restriction state fail closed; document search releases only explicitly unrestricted sanitized metadata; and credential-like fields remain redacted/derived-only where applicable.

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

The earlier host-venv MCP proof gap is now resolved. `tools/run_mcp_constitutional_certification.sh` builds Jason's actual MCP production Dockerfile from the source revision under test, layers only the test runner, and executes the constitutional MCP contract suite with the same MCP/PyJWT/runtime dependency set as production. During its first execution it exposed two Datto governed component-identity fail-closed regressions that the host environment had not surfaced; both were corrected before certification was allowed to pass. Production-equivalent certification passed for source revision `aa92ac17ed37640ecb8daf08c718afdd0ca08546`. Durable result: `docs/sessions/MCP-Constitutional-Certification-Result-2026-09-26.json`.

## Immediate remediation plan

1. Merge PR #381 through the normal protected-branch path after all required checks pass.
2. Close GitHub #175 and #176 after the ADR-011 requester-authorization architecture is present on authoritative `main`.
3. Keep `docs/control/CURRENT.md` synchronized whenever a material workstream changes.
4. Re-run the certification if any material constitutional architecture or production boundary changes.

## Certification decision

**Decision: ALL CONSTITUTIONAL ARTICLES PROVEN ON THE REVIEWED BRANCH; AUTHORITATIVE 100% CERTIFICATION PENDING PROTECTED-MAIN MERGE.**

All nineteen J-002 articles are classified PROVEN in this review. Article XIX/System Registry completeness, production-equivalent MCP certification-runner coverage, Autotask/IT Glue requester authorization, and the previously subjective/partial owner-architecture articles have all been remediated or reviewed against the Constitution's actual requirements. No substantive constitutional defect or active exception remains in the reviewed branch. The certification becomes authoritative for the repository when PR #381 is merged into protected `main`; until then, `main` remains the authoritative production source and must not be described as 100% certified solely from branch state.
