# Project Jason — Extension Construction Map

**Status:** Active continuity/control record
**Owner:** Jason Architecture Authority
**Purpose:** Give future sessions one place to determine how to create or extend a Jason component without rediscovering platform fundamentals or bypassing governance.

This map is not a new architecture authority. It points to the governing architecture, standards, component contracts, engineering guides, implementation exemplars, and completion controls for each extensible component class.

## Rule

Before creating a new Jason component or substantial variant, identify its class here and follow the referenced construction path.

If the class is missing, or the referenced material is not sufficient to reproduce the pattern safely, the missing construction guidance is a documentation defect that must be corrected before the new pattern is considered complete.

## Universal extension lifecycle

Every material extension follows this sequence unless a higher-authority record defines a stricter sequence:

**Need → classify component → read governing fundamentals → reuse existing pattern → define contract → establish identity/authority/policy → implement behind approved boundaries → deterministic tests/conformance → register operational entities when applicable → deploy through governed procedure → observe/verify → preserve evidence → lifecycle/documentation closeout.**

Working code alone is not completion.

## Construction map

| Component class | Start here | Existing reusable pattern / implementation guidance | Non-negotiable completion points |
|---|---|---|---|
| Provider / connector | `docs/engineering/jis/JIS-Provider-Development-Guide.md` | JIS provider template, completion checklist, provider engineering records, existing provider implementations/tests | Named capabilities/operations; governed authentication and secret references; provider-neutral shared infrastructure; authority/policy not embedded in connector; structured errors/results; audit/correlation; deterministic tests; System Registry registration/verification when production-bound |
| Capability / resource | `docs/architecture/J-101-Capability-Registry.md` and `docs/engineering/capabilities/Capability-Registry.md` | Existing CAP records and capability registry/runtime composition/tests | Stable capability name and contract; execution/permission mode; scope; provider-resolution rules; evidence semantics; deterministic tests; registry/provider metadata; no workflow-specific bypass |
| Natural-language resource inquiry / evidence selection | `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md` | Production endpoint inquiry, bounded evidence index, Ollama inquiry/evidence reasoners, runtime composition, focused tests | Separate selectors from facts; derive language vocabulary from governed capability metadata; request the smallest fact set; route only through Central Orchestrator; bound model evidence choices to Jason-supplied pointers; deterministic dereference; source attribution; no bespoke question-specific script |
| Agent / reasoning component | `docs/architecture/J-100-Reference-Architecture.md` plus `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` | Existing bounded reasoning/resource-inquiry implementations and tests are exemplars, not authority | Agent may interpret/reason and return structured results or request named capabilities; no direct agent-to-agent, provider, secret-store, or business-authority path; bounded context; deterministic authority/provider/fact resolution remains outside model discretion; auditable failure behavior |
| Governance / policy gate | `docs/architecture/J-102-Governed-Approval-Architecture.md` and `docs/components/kernel/JKD-004-Execution-Policy-Engine.md` | Existing authority/policy/approval gates and tests | Explicit trigger and inputs; allowed outcomes; fail-closed semantics; authority distinction; evidence/audit; escalation/approval behavior; no hidden policy inside connector/agent/workflow code; deterministic tests |
| Ingress / interface adapter | `docs/architecture/J-100-Reference-Architecture.md` and relevant ADRs | OpenClaw/Teams ingress records and implementation/tests | Establish trusted machine/user identity; preserve correlation; construct governed orchestration request; no provider bypass; deterministic rejection/failure classification; governed return path; security audit; transport remains replaceable |
| Identity / authority component | `docs/components/kernel/JKD-001-Identity-and-Authority-Service.md` | JKD-001 runtime foundation, grant/delegation tooling and tests | Identity before authority; narrow capability/scope grants; explicit delegation semantics; auditable mutation; fail closed on ambiguity/missing authority; no authority inferred from technical access |
| Secret / credential integration | `docs/components/kernel/JKD-003-Secrets-Broker.md` and `docs/operations/Provider-Secret-Provisioning.md` | OpenBao provider lifecycle tooling and secret-provider records | Secret references only; no secret values in docs/System Registry/audit; least privilege; runtime access verification; rotation/revocation/recovery; provider-specific credentials remain behind broker/provider boundary |
| Internal service / runtime component | `docs/architecture/J-100-Reference-Architecture.md`, relevant JKD/INF record, and deployment architecture | `jason-runtime`, OpenBao, OpenClaw deployment/runbook patterns; `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` | Defined responsibility and dependency boundary; service identity; network/secret mounts by reference; health verification; hardened runtime controls; rollback; System Registry declared/observed/verified state; derive deployment topology/inputs from authoritative live state rather than assumption |
| System Registry entity / verification method | `docs/architecture/J-103-System-Registry.md` | `implementation/kernel/system_registry/` schemas, repository, probes, verifier, lifecycle tests | Declared versus observed versus verified separation; no secrets; append-only lifecycle evidence; bounded verification; no silent remediation; authority/governance for mutation |
| Evidence / audit component | `docs/components/kernel/JKD-002-Evidence-and-Memory-Service.md` | Existing orchestration/security audit stores and proof/session records | Correlation/provenance; sanitization; append-only or governed history as appropriate; evidence pointer integrity; distinguish assertion from proof; no credential leakage |
| Approval / communication action | `docs/architecture/J-102-Governed-Approval-Architecture.md` plus capability-specific records | CAP-007 and approval-request patterns | Business authority remains explicit; deterministic policy/approval state; provider action only after authorization; response/evidence retained; retries/duplicates handled safely |
| Deployment / operational procedure | `docs/operations/README.md` and relevant INF/runbook | Existing runtime/OpenBao/provider deployment runbooks; `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` | Prerequisites; authority; observation vs mutation; stop conditions; rollback; verification; evidence retention; no secret printing; no silent drift repair; deployment failure reports an error without unnecessarily terminating the operator's interactive session |

## Universal no-bypass checks

Before implementation approval, verify:

- No agent directly calls another agent.
- No agent/interface directly invokes an external provider around the Central Orchestrator.
- No connector embeds business authority or policy that belongs in governance/policy services.
- No capability silently depends on a one-off script when a reusable capability/resource can represent the operation.
- No secret value is stored or transported where only a credential reference is required.
- No production component/capability/provider is treated as operational without the required System Registry registration and verification.
- No current runtime claim is taken from conversation memory or a stale narrative document.
- Natural-language resource questions do not become bespoke workflow scripts merely because semantic interpretation or evidence selection failed.

## Universal extension Definition of Done

Before calling an extension complete, a future session must be able to find, without chat history:

1. the governing architecture/standard/ADR;
2. the component/capability/provider contract;
3. the closest reusable implementation pattern;
4. identity/authority/policy/approval requirements;
5. secret and data-handling requirements;
6. deterministic tests/conformance checks;
7. deployment/rollback/verification procedure where applicable;
8. System Registry registration/lifecycle requirements where applicable;
9. durable proof/evidence of the result where applicable; and
10. the documentation updates required to create the next component of the same class.

## Documentation-impact rule

Every material implementation workstream must make an explicit documentation-impact determination.

If it introduces a new reusable pattern, changes how an existing class is constructed, or exposes a missing prerequisite that had to be rediscovered, this map and the owning construction guidance must be updated in the same governed workstream.

"No documentation impact" is an explicit reviewed conclusion, not the result of forgetting to update documentation.

## 2026-08-12 construction guidance refinement

Resource inquiry/evidence work now has a durable reusable guide at `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md`.

For capability/resource extensions that answer natural-language questions, use that guide together with the existing Capability / resource construction row above. It captures selector/fact separation, capability-derived canonical fact hints, minimal requested facts, relevance-bounded evidence indexing, bounded model-selected pointers, and deterministic provider-evidence dereference.

Runtime rebuild/deploy rediscovery exposed a missing operational prerequisite. Use `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` for the current deployment construction/verification pattern, including Compose-label discovery, required interpolation inputs, protected secret-path checks, and the interactive-shell no-unconditional-exit rule.

<!-- BEGIN PROVIDER ADAPTATION FOUNDATION -->
## Provider Adaptation and Resource Outcome Foundation

**Status:** Production foundation operational

Implemented foundations:

- provider-neutral governed Datto read capabilities;
- organization-level provider-read authority matching;
- deterministic-first natural-language resource interpretation;
- Ollama semantic fallback for non-deterministic interpretation;
- resource inquiry result intent;
- resource inquiry completeness requirements;
- structurally authoritative direct evidence;
- generic bounded provider adaptation;
- provider contradiction detection;
- provider pagination recovery;
- complete collection aggregation;
- bounded collection rendering;
- provider adaptation audit evidence.

Primary implementation areas:

- `implementation/orchestrator/conversation_resource_intent.py`
- `implementation/orchestrator/resource_inquiry.py`
- `implementation/orchestrator/resource_reasoner.py`
- `implementation/orchestrator/resource_evidence.py`
- `implementation/orchestrator/provider_read_authority.py`
- `implementation/connectors/core/provider_adaptation.py`
- `implementation/connectors/datto_rmm/connector.py`
- `implementation/runtime_service/src/jason_runtime/composition.py`

Architecture reference:

`docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md`

Production proof:

`docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md`

Future construction:

- observed provider-behavior profiles;
- provider drift detection;
- generalized continuation-token handling;
- rate-limit adaptation;
- native Teams processing feedback;
- separately governed provider write surfaces.
<!-- END PROVIDER ADAPTATION FOUNDATION -->
