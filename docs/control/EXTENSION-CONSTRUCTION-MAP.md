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
| Natural-language resource inquiry / evidence selection | `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md` and `docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md` | Production endpoint/site inquiries, deterministic metadata interpreter, bounded evidence index, Ollama fallback/evidence reasoners, runtime composition, focused tests | Separate selectors from facts; separate `inquiry_hints` from returnable `fact_hints`; declare canonical `collection_fact` for collection capabilities; normalize exhaustive/count language to canonical collection evidence; propagate result intent/completeness through planning; route only through Central Orchestrator; deterministic dereference/source attribution; no bespoke question-specific script |
| Semantic capability gap / provider documentation discovery | `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md` | Bounded semantic intent planning, capability-gap assessment, registered-provider discovery, governed documentation source registry, OpenAPI source adapter/interpreter, semantic-evidence and corroborating-evidence reviewers | Fail closed when registered capabilities cannot support requested facts; inspect only governed registered providers and approved authoritative documentation sources; documentation findings are candidate evidence only; textual similarity never establishes semantic proof; semantic mappings require separately governed proposal/approval before registry activation; no provider execution or credential access during documentation discovery |
| Agent / reasoning component | `docs/architecture/J-100-Reference-Architecture.md` plus `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` | Existing bounded reasoning/resource-inquiry implementations and tests are exemplars, not authority | Agent may interpret/reason and return structured results or request named capabilities; no direct agent-to-agent, provider, secret-store, or business-authority path; bounded context; deterministic authority/provider/fact resolution remains outside model discretion; auditable failure behavior |
| Governance / policy gate | `docs/architecture/J-102-Governed-Approval-Architecture.md` and `docs/components/kernel/JKD-004-Execution-Policy-Engine.md` | Existing authority/policy/approval gates and tests | Explicit trigger and inputs; allowed outcomes; fail-closed semantics; authority distinction; evidence/audit; escalation/approval behavior; no hidden policy inside connector/agent/workflow code; deterministic tests |
| Ingress / interface adapter | `docs/architecture/J-100-Reference-Architecture.md` and relevant ADRs, including `docs/decisions/ADR-007-Teams-Proactive-Messaging.md` | OpenClaw/Teams ingress records and implementation/tests; `infrastructure/openclaw-jason-bridge/`; `implementation/connectors/openclaw/src/jason_openclaw/conversation_ingress.py` | Establish trusted machine/user identity; preserve correlation; construct governed orchestration request; no provider bypass; deterministic rejection/failure classification; governed return path; security audit; transport remains replaceable; user-visible processing feedback, when used, is bounded/non-authoritative and must not expose reasoning or alter execution authority; transport-feedback failure must not silently replace the governed result; exact authenticated transport-message retries must be durably idempotent at governed ingress before flow/orchestration using stable authenticated transport identity rather than request text; duplicate suppression must be auditable; same-text new message IDs remain distinct requests unless a deeper governed capability explicitly defines other idempotency semantics |
| Identity / authority component | `docs/components/kernel/JKD-001-Identity-and-Authority-Service.md` | JKD-001 runtime foundation, grant/delegation tooling and tests | Identity before authority; narrow capability/scope grants; explicit delegation semantics; auditable mutation; fail closed on ambiguity/missing authority; no authority inferred from technical access |
| Secret / credential integration | `docs/components/kernel/JKD-003-Secrets-Broker.md` and `docs/operations/Provider-Secret-Provisioning.md` | OpenBao provider lifecycle tooling and secret-provider records | Secret references only; no secret values in docs/System Registry/audit; least privilege; runtime access verification; rotation/revocation/recovery; provider-specific credentials remain behind broker/provider boundary |
| Internal service / runtime component | `docs/architecture/J-100-Reference-Architecture.md`, relevant JKD/INF record, and deployment architecture | `jason-runtime`, OpenBao, OpenClaw deployment/runbook patterns; `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` | Defined responsibility and dependency boundary; service identity; network/secret mounts by reference; health verification; hardened runtime controls; rollback; System Registry declared/observed/verified state; derive deployment topology/inputs from authoritative live state rather than assumption |
| System Registry entity / verification method | `docs/architecture/J-103-System-Registry.md` | `implementation/kernel/system_registry/` schemas, repository, probes, verifier, lifecycle tests | Declared versus observed versus verified separation; no secrets; append-only lifecycle evidence; bounded verification; no silent remediation; authority/governance for mutation |
| Evidence / audit component | `docs/components/kernel/JKD-002-Evidence-and-Memory-Service.md` | Existing orchestration/security audit stores and proof/session records | Correlation/provenance; sanitization; append-only or governed history as appropriate; evidence pointer integrity; distinguish assertion from proof; no credential leakage |
| Approval / communication action | `docs/architecture/J-102-Governed-Approval-Architecture.md` plus capability-specific records | CAP-007 and approval-request patterns | Business authority remains explicit; deterministic policy/approval state; provider action only after authorization; response/evidence retained; retries/duplicates handled safely |
| Deployment / operational procedure | `docs/operations/README.md` and relevant INF/runbook | Existing runtime/OpenBao/provider deployment runbooks; `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` | Prerequisites; authority; observation vs mutation; stop conditions; rollback; verification; evidence retention; no secret printing; no silent drift repair; deployment failure reports an error without unnecessarily terminating the operator's interactive session; rollback success must verify restored state/content rather than merely process restart |

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
- User-facing processing feedback is not treated as authorization, evidence, completion, or reasoning output.
- No exact retry of an authenticated transport activity may initiate duplicate governed work when a stable authenticated message/activity identity exists; do not substitute text-similarity heuristics for transport identity.

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

## 2026-08-14 Teams processing-feedback construction refinement

Jason-bound Teams conversations currently use the OpenClaw `jason-bridge` compatibility pre-agent path. Because this path can complete the Teams turn before OpenClaw's normal agent/reply lifecycle, OpenClaw's native typing lifecycle is not sufficient evidence that a governed Jason request is visibly processing.

The reusable transport pattern is therefore:

1. validate the required inbound Teams transport identity/conversation fields;
2. emit a static, best-effort acknowledgement through OpenClaw's supported channel outbound adapter;
3. continue the existing governed Jason request path unchanged;
4. treat acknowledgement failure as a transport-feedback failure, not as authority to fail or bypass the governed request;
5. return only the final governed Jason response/error as the authoritative outcome.

The acknowledgement must not disclose chain-of-thought, model reasoning, provider evidence, secrets, authorization state, or a claim of task completion. It is a user-experience signal only.

Reference proof: `docs/sessions/Teams-Processing-Feedback-Proof-2026-08-14.md`.

The same work exposed a rollback-verification construction rule: a rollback is not proven merely because a service restarted. Validate the restored artifact/state (for example by hash/source parity plus service health) before declaring rollback success.

## 2026-08-14 Teams exact-message idempotency construction refinement

The processing acknowledgement reduces uncertainty for the user but is not an idempotency control. Exact duplicate transport activities must be suppressed centrally even if OpenClaw constructs a fresh Jason request envelope for a retry.

The reusable ingress pattern is:

1. authenticate and validate the signed transport envelope and machine identity;
2. validate freshness and preserve the existing request-ID replay claim;
3. derive a stable exact-message identity only from authenticated transport identity/correlation fields, not from message text;
4. for Teams, scope that identity by Microsoft tenant ID, Microsoft object ID, conversation ID, and message ID;
5. hash the compound identity before using it as a persistent claim key;
6. durably and atomically claim the exact-message key before entering the conversation flow or Central Orchestrator;
7. if already claimed, emit an auditable duplicate-suppression event and return an idempotent duplicate transport result without starting governed execution;
8. allow a distinct authenticated message ID to proceed even when text matches an earlier request; and
9. treat capability/action-level side-effect idempotency as a separate deeper control when consequential operations require it.

Current implementation reuses `SQLiteReplayStore` and the `teams-message-v1:` claim namespace. The duplicate transport result is HTTP `200`, `status=duplicate`, `error_code=duplicate_message`.

The ingress concurrency regression test proves the second exact-message retry is suppressed while the first ingress flow is still active. The current production HTTP server remains single-worker, so future multi-worker/replica scale-out must retain an atomic shared idempotency state layer before concurrency topology changes.

Reference proof: `docs/sessions/Teams-Exact-Message-Idempotency-Proof-2026-08-14.md`.

The same work exposed two reusable validation/deployment prerequisites now owned by `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md`: host runtime tests must expose the same source roots as the runtime Docker image, and protected secret bind sources may require a Docker daemon bind-probe when the ordinary operator cannot traverse the host path.

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
- separately governed provider write surfaces.
<!-- END PROVIDER ADAPTATION FOUNDATION -->

<!-- BEGIN SEMANTIC CAPABILITY DISCOVERY FOUNDATION -->
## Semantic Capability Discovery and Documentation Evidence Foundation

**Status:** Governed observe-only foundation validated 2026-08-13

When a natural-language request identifies a requested fact that cannot be satisfied by the currently registered capability/evidence/derivation surface, Jason must not create a bespoke workflow or invent a provider mapping.

Use this bounded progression:

1. Semantic planning proposes only provider-neutral capabilities.
2. Plan sufficiency validates the proposal against the original requested facts.
3. Fulfillment feasibility fails closed when no governed fulfillment path exists.
4. A structured capability-registry gap is created under Technology Steward ownership.
5. Registered-provider discovery exposes only existing governed providers and their authoritative documentation sources.
6. Documentation-review planning creates bounded review targets.
7. A governed documentation source registry resolves symbolic documentation names to approved source definitions.
8. Provider-neutral source adapters retrieve documentation only through approved bounded transports.
9. Documentation interpretation may surface candidate operations, schemas, and fields.
10. Semantic-evidence review and corroborating-evidence review determine whether the documentation is strong enough to permit a mapping proposal.
11. Documentation evidence never approves or activates a semantic mapping.
12. Registration or activation requires normal governance, evidence, versioning, and approval.

Non-negotiable rules:

- Documentation similarity is not semantic proof.
- A model may not invent provider mappings, derivations, capabilities, or evidence authority.
- Documentation discovery does not grant provider execution authority.
- No credentials are required for public documentation review.
- Provider/source/fact scope is carried from the governed review target and enforced by the reader.
- Documentation reads are bounded, provenance-addressed, and fail closed.
- An ambiguous result remains unresolved rather than being guessed.
- Provider-specific discoveries must improve the reusable source/semantic architecture rather than create question-specific code.

Current validated implementation includes:

- `implementation/orchestrator/semantic_intent_planning_loop.py`
- `implementation/orchestrator/semantic_planning_bootstrap.py`
- `implementation/orchestrator/semantic_plan_sufficiency.py`
- `implementation/orchestrator/semantic_fulfillment_feasibility.py`
- `implementation/orchestrator/semantic_capability_gap.py`
- `implementation/orchestrator/provider_capability_discovery.py`
- `implementation/orchestrator/provider_documentation_review.py`
- `implementation/orchestrator/provider_documentation_reader.py`
- `implementation/orchestrator/provider_documentation_source_registry.py`
- `implementation/orchestrator/provider_documentation_source_catalog.py`
- `implementation/orchestrator/openapi_documentation_source_adapter.py`
- `implementation/orchestrator/https_documentation_transport.py`
- `implementation/orchestrator/openapi_documentation_interpreter.py`
- `implementation/orchestrator/provider_semantic_evidence_review.py`
- `implementation/orchestrator/provider_corroborating_evidence_review.py`

Historical proof:

`docs/sessions/Governed-Semantic-Capability-Discovery-Proof-2026-08-13.md`
<!-- END SEMANTIC CAPABILITY DISCOVERY FOUNDATION -->
