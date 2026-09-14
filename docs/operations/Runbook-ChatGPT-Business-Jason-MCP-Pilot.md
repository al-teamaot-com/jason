# Runbook — ChatGPT Business + Jason MCP Pilot

**Status:** Active operational runbook for MCP-001/MCP-002  
**Updated:** 2026-09-11  
**Owner:** Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`

## Purpose

Provide the controlled sequence for building, deploying, verifying, operating, and rolling back Jason as a ChatGPT Business MCP/custom app without disrupting the existing Teams/OpenClaw production baseline or bypassing Jason governance.

This runbook does not grant capability, provider, disclosure, or production-change authority by itself. Required approvals remain separate.

## Preconditions

Before pilot publication or production replacement:

- current Git branch and exact source commit identified from GitHub;
- current System Registry and host state reviewed;
- existing Teams/Jason production baseline captured;
- MCP service implementation passes deterministic tests and required CI;
- MCP service has a defined System Registry entity/lifecycle record;
- supported ChatGPT Business MCP/custom app connection method verified against current OpenAI documentation;
- caller authentication design approved;
- read-only capability allowlist approved;
- provider credentials available only through existing Jason secret boundaries;
- rollback/disable procedure and known-good image/container identified;
- no action/write tools exposed unless separately authorized.

## Current production deployment boundary

Current topology is volatile operational state and must be re-derived before every mutation. The following is a **point-in-time observation from 2026-09-11**, not a perpetual inventory:

- MCP container observed running as `jason-mcp-pilot`;
- MCP image observed as `jason-mcp:information-auth-568a9b984ad7`;
- MCP container restart policy observed as `no` and no Docker healthcheck was configured;
- Docker labels on the MCP container identified Compose project/service values, but did **not** provide Compose working-directory or Compose-file labels;
- the separate `jason-runtime` container was healthy and was Compose-managed from a deployment snapshot under `/home/al/jason-deployments/`;
- a pre-hardening MCP rollback container/image remained preserved;
- the primary `/home/al/projects/jason` worktree contained unrelated changes and was not a valid deployment source.

Operational consequence: **do not assume the MCP container is recreated by the same Compose file that manages `jason-runtime`.** The current MCP launch/recreation inputs must be derived from the running MCP deployment and accepted source/build records before replacement. If those inputs cannot be reconstructed without guessing or exposing secrets, stop the deployment and repair the deployment record first.

The runtime and MCP are separate deployment units. A source change limited to `implementation/mcp_service` must not trigger a `jason-runtime` rebuild unless the change explicitly requires it.

## Source and worktree rules

Production MCP builds must come from a clean isolated checkout/worktree pinned to the exact approved GitHub source commit.

Never deploy from `/home/al/projects/jason` merely because it is convenient. If that protected worktree is dirty, leave it untouched. Do not reset, clean, stash, switch, or otherwise disturb unrelated work to make it deployable.

Before building:

1. fetch the authoritative branch head from GitHub;
2. verify the intended commit exists on that branch;
3. verify the exact code change boundary;
4. verify relevant CI/tests for the source commit;
5. create/use a clean isolated checkout pinned to the approved commit;
6. run `git diff --check` and focused deterministic tests;
7. record the source SHA used for the image build.

Documentation-only commits made after an approved source commit do not silently expand the approved production source scope. Deploy the exact approved source SHA unless a later source SHA is separately accepted.

## MCP image build rule

The authoritative Docker build definition is `infrastructure/jason-mcp/Dockerfile`.

That Dockerfile requires a `BASE_IMAGE` build argument and installs the MCP package from repository source. Do not invent a base image. Derive the proven base-image input from the accepted build/deployment record or fresh non-secret host evidence. If the base cannot be positively established, stop rather than substituting a plausible image.

Tag candidate images so the source commit is traceable from the image name or deployment evidence. Preserve the exact resulting image ID in the deployment proof.

Do not bake provider credentials, OAuth client secrets, OpenBao tokens, RoleIDs/SecretIDs, or other secret values into the image or build arguments.

## MCP production replacement sequence

This sequence governs an approved MCP-only source promotion:

1. **Observe:** verify current `jason-mcp-pilot` state, image ID/tag, public health behavior, MCP tool surface, and read-only/governed status.
2. **Pin:** verify the exact approved GitHub source commit and required CI result.
3. **Isolate:** use a clean isolated checkout/worktree at that source SHA.
4. **Build:** build a new MCP candidate from `infrastructure/jason-mcp/Dockerfile` using the positively established base image; do not mutate the running container.
5. **Preserve rollback:** retain the exact current image and preserve/rename the current container as a timestamped rollback artifact before replacement. Never delete earlier rollback material as part of the forward deployment.
6. **Reconstruct launch safely:** reproduce the existing MCP network, port publishing, mounts, identity/authentication inputs, and non-secret configuration from accepted deployment evidence or current Docker metadata. Never print full environment-variable arrays or secret contents to reconstruct the command.
7. **Start candidate:** create/start the candidate as the production MCP container using the same required deployment boundary. Do not restart `jason-runtime`, Teams, OpenClaw, OpenBao, or observability merely because MCP changed.
8. **Bounded health:** verify the health endpoint/public route within a bounded timeout.
9. **Transport/authentication:** verify anonymous MCP access is rejected, supported public Host/Origin behavior is preserved, and OAuth metadata/Entra authentication remain correct.
10. **Surface:** verify the model-facing tool surface remains exactly the authorized read-only surface unless a separate authority change was approved.
11. **Governance:** verify `governed_execution=central-orchestrator`, `direct_provider_access=false`, and `write_tools_enabled=false` (or equivalent authoritative status fields).
12. **Functional proof:** run the smallest harmless governed live read needed to prove the changed behavior. Do not use provider writes as a deployment smoke test.
13. **Parity:** verify the running container image ID matches the candidate image ID and preserve the source SHA -> image ID -> live container relationship as deployment evidence.
14. **Record:** update the applicable session/proof record and System Registry lifecycle/verification record when required.

### Important reconstruction constraint

At the 2026-09-11 observation, the MCP container did not expose Compose working-directory/config-file labels. Therefore this runbook intentionally does not fabricate an exact `docker compose` command for MCP. A future operator must use the then-current accepted MCP deployment mechanism or derive the current Docker launch inputs without displaying secrets. If an exact durable launch mechanism is later standardized (for example a dedicated Compose/service definition or deployment script), this runbook must be updated and that mechanism becomes the preferred source of truth.

## MCP rollback sequence

Rollback success is more than seeing a process start.

If the candidate fails acceptance:

1. stop/remove only the failed MCP candidate as needed;
2. restore the preserved known-good MCP container/image using the exact pre-change image identity and deployment inputs;
3. verify the expected MCP container is running;
4. verify public health/route behavior;
5. verify OAuth/authentication and hostile Host/Origin protections still behave as expected;
6. verify the exact authorized read-only tool surface;
7. verify Central Orchestrator-only governed execution and absence of direct provider/write access;
8. run one harmless governed read;
9. record rollback image/container identity and proof result.

Do not destroy provider credentials, modify provider security levels, or roll back `jason-runtime` merely to undo an MCP-only code deployment unless independent evidence shows those components were also changed.

## Capability discovery behavior

`discover_capabilities.operation` is an exact registry metadata filter, not a direct synonym for conversational verbs such as “read,” “get,” or “show.” A resource may legitimately support an exact lookup through a `search` operation rather than an active `read` operation.

The MCP capability-discovery implementation should therefore remain fail-closed for exact execution while allowing model-facing discovery to return safe same-resource active read-only alternatives when an exact operation filter has no match. An alternative is guidance only; it does not activate a capability, bypass `_dynamic_capability_allowed`, or grant execution/release authority.

For example, an exact ticket-number lookup may be served by an active ticket `search` capability even when ticket `read` is not activated. Do not activate an additional capability merely to make natural-language wording line up with a registry operation label.

## Phase A — Preserve existing baseline

Capture before changing production exposure:

- `jason-runtime` service health/state;
- `jason-teams-gateway` state and host port ownership;
- OpenClaw state and currently justified functions;
- current System Registry declared/observed/verified status;
- current MCP source/image/container identifiers;
- current rollback MCP image/container;
- relevant Teams/MCP smoke proof.

Do not remove or reconfigure Teams/OpenClaw merely to start or update the MCP path.

## Phase B — Local MCP proof

Verify locally before ChatGPT publication:

1. service starts cleanly;
2. no secret values are emitted;
3. health/readiness succeeds;
4. only approved read tools enumerate;
5. tool names/descriptions are capability/resource oriented;
6. each tool maps internally to a governed Jason capability;
7. Central Orchestrator is the only provider execution coordinator;
8. direct connector/provider invocation from MCP is impossible by contract/test;
9. unsupported/unauthorized requests fail closed;
10. evidence/provenance/audit are recorded;
11. deterministic complete-data analysis works for large collections;
12. service disable/restart/rollback is proven.

## Phase C — Identity proof

Using the actual supported ChatGPT Business custom app/MCP identity mechanism:

- prove caller identity is available and trustworthy enough for the chosen design;
- map caller to Jason principal;
- prove expected AOT user access;
- prove unknown/unmapped user rejection;
- prove organization/client scope;
- prove action authority is not inferred from app access;
- record bounded evidence of the identity mapping behavior.

Stop if the current Business/MCP platform cannot provide an identity mechanism adequate for Jason's governance requirements.

## Phase D — Limited ChatGPT Business publication

Publish only to the smallest practical AOT pilot scope supported by the workspace/app controls.

Initial tool scope: low-risk governed reads only.

Do not expose writes/actions.

## Pilot test matrix

### Natural conversation

- arbitrary wording for existing resource reads;
- pronoun/follow-up questions in same ChatGPT session;
- question refinement without Jason-specific syntax;
- comparisons and summaries across multiple reads.

### Provider behavior

- endpoint lookup;
- endpoint audit/inventory;
- alert lookup;
- complete account/site collection question;
- exact count using deterministic Jason analysis;
- incomplete/provider-error case.

### Cross-provider behavior

After a second provider is enabled:

- read from provider A;
- use result/context to request provider B evidence;
- synthesize answer in ChatGPT;
- confirm Jason did not require a bespoke workflow for that wording.

### Security/governance

- unknown identity;
- unauthorized capability;
- invalid client scope;
- cross-client attempt;
- retired/unavailable capability;
- secret-like field request;
- write/action request during read-only pilot;
- provider timeout/rate limit.

### Cost

For ordinary read-only ChatGPT-originated tool use:

- record Jason-side hosted-model calls;
- target: zero additional conversational/reasoning calls;
- identify any unavoidable Jason-side model dependency;
- attribute its cost separately.

## Acceptance criteria

Pilot/promotion may advance only if:

- ChatGPT technician experience is materially more fluid than the custom Teams reasoning path;
- Jason identity/authority boundaries remain intact;
- no provider credential is exposed;
- client isolation is proven;
- Central Orchestrator remains sole execution coordinator;
- exact collection questions work when source evidence is complete;
- provenance/audit is available for each tool execution;
- no question-specific handler is required;
- duplicate Jason-side model use is absent by default;
- latency is acceptable for technician use;
- rollback/disable is proven.

## Stop conditions

Stop promotion or expansion if any of the following occur:

- caller identity cannot be established reliably;
- cross-client/tenant scope can be manipulated by the model;
- provider credentials or sensitive secrets reach ChatGPT;
- MCP can bypass Central Orchestrator;
- actions become reachable without explicit authorization/approval design;
- audit/provenance cannot correlate tool execution;
- tool execution becomes dependent on question-specific workflow code;
- ChatGPT Business workspace/app controls are insufficient for the approved risk posture;
- current deployment inputs cannot be reconstructed without guessing;
- the exact rollback image/container cannot be identified;
- a proposed provider/security change exceeds its explicitly approved least-privilege scope.

## Evidence to preserve

For each MCP deployment/pilot milestone preserve without secrets:

- repository source commit;
- image tag and image ID;
- prior/rollback image and container identity;
- System Registry lifecycle/verification record;
- service/public health verification result;
- tool enumeration snapshot;
- identity-binding proof;
- representative governed read/provenance;
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
- read-only acceptance criteria pass;
- current rollback is preserved and verified;
- runbook/rollback information is current;
- documentation distinguishes intended state from fresh observed operational state.
