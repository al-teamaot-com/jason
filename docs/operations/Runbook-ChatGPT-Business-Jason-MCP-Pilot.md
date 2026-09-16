# Runbook — ChatGPT Business + Jason MCP Pilot

**Status:** Active operational runbook for ChatGPT/Jason governed reads and governed-action pilot  
**Updated:** 2026-09-16  
**Owner:** Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Current checkpoint:** `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`

## Purpose

Provide the controlled sequence for building, deploying, verifying, operating, and rolling back Jason as a ChatGPT Business MCP/custom app without disrupting the existing Teams/OpenClaw production baseline or bypassing Jason governance.

This runbook supports both governed reads and separately authorized governed actions. It does not grant capability, provider, disclosure, business, or production-change authority by itself. Required Jason grants, provider authority, and per-execution approvals remain separate.

## Durable operating principle

> **ChatGPT reasons. Jason governs and executes.**

The ChatGPT app/MCP surface is an interface to Jason governance. It is not a direct provider client, secret broker, or alternate execution authority.

## Preconditions

Before pilot publication, production replacement, or action-surface expansion:

- current Git branch and exact source commit identified from GitHub;
- current System Registry and fresh host/runtime state reviewed when relevant;
- existing Teams/Jason production baseline captured;
- MCP service implementation passes deterministic tests and required CI for the changed surface;
- MCP service has a defined System Registry entity/lifecycle record where required;
- supported ChatGPT Business MCP/custom app connection method verified;
- caller identity design approved and working;
- active capability allowlist/grants approved;
- provider credentials available only through existing Jason secret boundaries;
- rollback/disable procedure and known-good image/container identified;
- any action/write capability is separately authorized, bounded, and approval-gated;
- direct provider access remains disabled.

## Current production deployment boundary

Current topology is volatile operational state and must be re-derived before a consequential production change.

The authoritative bounded state for the current governed-action pilot is recorded in `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`.

At that checkpoint:

- live MCP service: `jason-mcp-pilot`;
- last observed deployed MCP image: `jason-mcp:generic-governed-289bdfe957ed`;
- deployed source: `289bdfe957ed6644f6ca25d70f0d558d54478cd3`;
- live mode: `governed-read-plus-actions`;
- Central Orchestrator execution: enabled;
- direct provider access: disabled;
- active write/action capabilities reported by MCP:
  - `automation.component.execute`;
  - `service.ticket.note.create`;
  - `service.ticket.update`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

Current Git may be ahead of deployed runtime. A later source commit must not be described as deployed merely because it is the branch head.

The runtime and MCP remain separate deployment units. A source change limited to `implementation/mcp_service` must not trigger a `jason-runtime` rebuild unless the change explicitly requires it.

## Source and worktree rules

Production MCP builds must come from a clean isolated checkout/worktree pinned to the exact approved GitHub source commit.

Never deploy from a protected or dirty worktree merely because it is convenient. Do not reset, clean, stash, switch, or otherwise disturb unrelated work to make it deployable.

Before building:

1. fetch the authoritative branch head from GitHub;
2. verify the intended source commit exists on that branch;
3. distinguish source-only/documentation-only commits from the exact approved deployment source;
4. verify the exact code-change boundary;
5. verify relevant CI/tests for the source commit;
6. create/use a clean isolated checkout pinned to the approved commit;
7. run deterministic validation appropriate to the change;
8. record the source SHA used for the image build.

Documentation-only commits made after an approved source commit do not silently expand the approved production source scope.

## MCP image build rule

The authoritative Docker build definition is `infrastructure/jason-mcp/Dockerfile`.

That Dockerfile requires a `BASE_IMAGE` build argument. Do not invent a base image. Derive the proven base-image input from accepted build/deployment evidence or fresh non-secret host evidence.

Tag candidate images so the source commit is traceable. Preserve the exact resulting image ID in deployment evidence.

Do not bake provider credentials, OAuth client secrets, OpenBao tokens, RoleIDs/SecretIDs, or other secret values into the image or build arguments.

## MCP production replacement sequence

This sequence governs an approved MCP-only source promotion:

1. **Observe:** verify current `jason-mcp-pilot` state, image ID/tag, public health behavior, delivered tool surface, MCP self-reported capability state, and governance status.
2. **Pin:** verify the exact approved GitHub source commit and required CI result.
3. **Isolate:** use a clean isolated checkout/worktree at that source SHA.
4. **Build:** build a new MCP candidate from the authoritative Dockerfile using the positively established base image; do not mutate the running container.
5. **Preserve rollback:** retain the exact current image and preserve/rename the current container as a timestamped rollback artifact before replacement.
6. **Reconstruct launch safely:** reproduce required network, port publishing, mounts, identity/authentication inputs, and non-secret configuration from accepted deployment evidence/current Docker metadata. Never print full environment arrays or secret contents.
7. **Start candidate:** create/start the candidate using the accepted MCP deployment boundary. Do not restart unrelated services merely because MCP changed.
8. **Bounded health:** verify health/public route within a bounded timeout.
9. **Transport/authentication:** verify anonymous access rejection, supported Host/Origin behavior, OAuth metadata, and Entra authentication.
10. **Surface:** verify the model-facing tool surface matches the explicitly authorized profile. For the governed-action pilot, the backend may include the generic governed execution tool; do not infer client delivery solely from backend registration.
11. **Governance:** verify `governed_execution=central-orchestrator`, `direct_provider_access=false`, and action/write state equals the approved profile.
12. **Read smoke proof:** run the smallest harmless governed read needed to prove the changed behavior.
13. **Action smoke proof:** do **not** use a provider mutation as a generic deployment smoke test. Run an action only when the specific action has separate authority/approval and the pilot requires it.
14. **Parity:** verify running image ID equals candidate image ID and preserve source SHA → image ID → live container relationship.
15. **Record:** update the applicable session/proof record, `CURRENT.md`, and System Registry lifecycle/verification records when required.

## MCP rollback sequence

Rollback success is more than seeing a process start.

If a candidate fails acceptance:

1. stop/remove only the failed MCP candidate as needed;
2. restore the preserved known-good MCP container/image using the exact pre-change image identity and deployment inputs;
3. verify expected MCP container is running;
4. verify public health/route behavior;
5. verify OAuth/authentication and hostile Host/Origin protections;
6. verify the expected authorized tool surface;
7. verify Central Orchestrator-only governed execution and `direct_provider_access=false`;
8. verify write/action state equals the intended rollback profile;
9. run one harmless governed read;
10. record rollback image/container identity and proof result.

Do not destroy provider credentials, modify provider security levels, or roll back unrelated services merely to undo an MCP-only code deployment unless independent evidence shows those components were also changed.

## Capability discovery behavior

`discover_capabilities.operation` is an exact registry metadata filter, not a synonym for conversational verbs such as “read,” “get,” or “show.” A resource may legitimately support an exact lookup through a `search` operation rather than an active `read` operation.

Discovery guidance does not activate a capability, bypass runtime capability gating, or grant execution/release authority.

For actions, the same principle applies: discovery/registration is not execution authority. The capability must be active, the requester must hold the exact Jason grant, any required approval must match the exact request digest/scope, and provider authority must independently permit the operation.

## Phase A — Preserve existing baseline

Capture before changing production exposure:

- `jason-runtime` service health/state;
- `jason-teams-gateway` state and host port ownership;
- OpenClaw state and currently justified functions;
- current System Registry declared/observed/verified status;
- current MCP source/image/container identifiers;
- current rollback MCP image/container;
- current MCP self-reported capability/action state;
- current ChatGPT-delivered Jason tool catalog;
- relevant Teams/MCP smoke proof.

Do not remove or reconfigure Teams/OpenClaw merely to update the MCP path.

## Phase B — Local MCP proof

Verify locally before ChatGPT publication:

1. service starts cleanly;
2. no secret values are emitted;
3. health/readiness succeeds;
4. only approved tools enumerate;
5. tool names/descriptions are capability/resource oriented;
6. each tool maps internally to a governed Jason capability;
7. Central Orchestrator is the only provider execution coordinator;
8. direct connector/provider invocation from MCP is impossible by contract/test;
9. unsupported/unauthorized requests fail closed;
10. evidence/provenance/audit are recorded;
11. deterministic complete-data analysis works for large collections;
12. service disable/restart/rollback is proven;
13. action tools cannot execute without the required exact grant/approval chain;
14. failed provider authorization does not fall back to a broader identity.

## Phase C — Identity proof

Using the actual supported ChatGPT Business custom app/MCP identity mechanism:

- prove caller identity is available and trustworthy enough for the chosen design;
- map caller to Jason principal;
- prove expected AOT user access;
- prove unknown/unmapped user rejection;
- prove organization/client scope;
- prove action authority is not inferred from app access;
- record bounded evidence of the identity mapping behavior.

Stop if the current Business/MCP platform cannot provide an identity mechanism adequate for Jason governance.

## Phase D — Limited ChatGPT Business publication

Publish only to the smallest practical AOT pilot scope supported by workspace/app controls.

The initial foundation was read-only. The current governed-action pilot may expose the generic governed execution action only when:

- backend capability is explicitly active;
- client/app permission mode permits delivery of the action while still prompting before changes as intended;
- Jason exact-grant and per-execution approval remain mandatory;
- provider-specific credential separation remains intact;
- direct provider access remains disabled.

ChatGPT app permission is an additional client-side gate. It must never be treated as Jason authorization.

## Phase E — Governed-action acceptance

For a bounded action pilot:

1. choose a controlled resource and reversible/low-risk operation;
2. obtain fresh governed pre-read evidence;
3. record the exact current value/state that will be changed or the exact component/target pair;
4. confirm the capability is active in Jason;
5. confirm requester exact grant;
6. obtain the required per-execution approval bound to the exact request;
7. execute only through `execute_governed_capability` / the approved generic governed-action path;
8. make exactly the approved provider attempt(s); do not broaden or retry through alternate credentials when authority fails;
9. require provider result classification;
10. require governed post-action readback/job verification;
11. preserve correlation/audit evidence;
12. update the bounded proof record and `CURRENT.md`.

A client confirmation prompt does not replace Jason per-execution approval. A user statement of general intent does not authorize a different target, capability, or argument digest.

## Current provider-specific acceptance state

### Autotask

Controlled test company: **XYZ Test Company**.

Controlled ticket: `T20191013.0001`.

The bounded `service.ticket.update` pilot successfully changed priority `3` → `2`, and a later independent governed read confirmed `priority=2`.

Do not repeat that mutation merely to prove the path again. Use the existing accepted evidence unless a new test is independently justified and approved.

### Datto RMM

Controlled endpoint: `AOT-50282`.

Controlled diagnostic component: `Get-DNS Settings AOT Ver 06042025-1`.

The first bounded `automation.component.execute` attempt reached Datto but received HTTP 403 and created no job. Treat this as provider authorization failure, not execution success.

Correct the dedicated execution identity's minimum quick-job authority while preserving bounded Device Visibility and API Component Level. Do not broaden `datto_rmm.readonly` or add unrelated Global Settings/read permissions merely for observability.

The retry requires separate approval and governed job/readback verification.

## Pilot test matrix

### Natural conversation

- arbitrary wording for existing governed reads;
- pronoun/follow-up questions in the same ChatGPT session;
- question refinement without Jason-specific syntax;
- comparisons and summaries across multiple reads;
- explicit user confirmation behavior for a governed action.

### Provider behavior

- endpoint lookup;
- endpoint audit/inventory;
- alert lookup;
- complete account/site collection question;
- exact count using deterministic Jason analysis;
- incomplete/provider-error case;
- provider-authorized action success case;
- provider authorization denial with no credential fallback;
- post-action readback/job verification.

### Cross-provider behavior

- read from provider A;
- use result/context to request provider B evidence;
- synthesize answer in ChatGPT;
- confirm Jason did not require a bespoke workflow for that wording.

### Security/governance

- unknown identity;
- unauthorized capability;
- missing exact action grant;
- missing/expired/mismatched approval;
- invalid client scope;
- cross-client attempt;
- retired/unavailable capability;
- secret-like field request;
- provider timeout/rate limit;
- provider 403/authorization failure;
- attempt to alter approved action arguments after approval;
- attempt to bypass Jason through a direct provider path.

### Cost

For ordinary ChatGPT-originated tool use:

- record Jason-side hosted-model calls;
- target: zero additional conversational/reasoning calls for deterministic provider reads/actions;
- identify any unavoidable Jason-side model dependency;
- attribute its cost separately.

## Acceptance criteria

Pilot/promotion may advance only if:

- ChatGPT technician experience is materially fluid enough for operational use;
- Jason identity/authority boundaries remain intact;
- no provider credential is exposed;
- client isolation is proven;
- Central Orchestrator remains sole execution coordinator;
- exact collection questions work when source evidence is complete;
- provenance/audit is available for each tool execution;
- no question-specific handler is required;
- duplicate Jason-side model use is absent by default;
- latency is acceptable for technician use;
- rollback/disable is proven;
- action capabilities execute only under exact grant + required per-execution approval;
- provider authorization failure fails closed without broader identity fallback;
- post-action verification proves the resulting durable state/job result.

## Stop conditions

Stop promotion or expansion if any of the following occur:

- caller identity cannot be established reliably;
- cross-client/tenant scope can be manipulated by the model;
- provider credentials or sensitive secrets reach ChatGPT;
- MCP can bypass Central Orchestrator;
- actions become reachable without exact Jason grant/approval design;
- audit/provenance cannot correlate tool execution;
- tool execution becomes dependent on question-specific workflow code;
- ChatGPT Business workspace/app controls are insufficient for the approved risk posture;
- current deployment inputs cannot be reconstructed without guessing;
- the exact rollback image/container cannot be identified;
- a proposed provider/security change exceeds explicitly approved least-privilege scope;
- provider failure causes an automatic retry through a broader credential;
- post-action state cannot be verified.

## Evidence to preserve

For each MCP deployment/pilot milestone preserve without secrets:

- repository source commit;
- image tag and image ID;
- prior/rollback image and container identity;
- System Registry lifecycle/verification record when applicable;
- service/public health verification result;
- backend MCP capability/status snapshot;
- client-delivered tool enumeration snapshot;
- identity-binding proof;
- representative governed read/provenance;
- action request scope and approval evidence reference;
- provider outcome and correlation/audit reference;
- post-action readback/job verification;
- failed-closed tests;
- cost/usage summary where relevant;
- ChatGPT pilot findings;
- rollback proof where tested.

## Production promotion

Do not call a new ChatGPT/Jason MCP source revision accepted in production until:

- the exact source and image identity are recorded;
- the service is represented in System Registry as required;
- declared/observed/verified state agrees for the relevant boundary;
- identity/authority/security proof passes;
- the authorized read/action profile passes acceptance;
- any live action pilot has independent approval and post-action verification;
- current rollback is preserved and verified;
- runbook/rollback information is current;
- documentation distinguishes intended state, observed state, verified state, and historical proof.
