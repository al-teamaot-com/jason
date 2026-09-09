# Runbook — ChatGPT Business + Jason MCP Pilot

**Status:** Draft operational runbook for MCP-001/MCP-002  
**Date:** 2026-09-08  
**Owner:** Platform Owner  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`

## Purpose

Provide the controlled sequence for proving and piloting Jason as a ChatGPT Business MCP/custom app without disrupting the existing Teams/OpenClaw production baseline.

This runbook does not authorize deployment by itself.

## Preconditions

Before pilot publication:

- current Git branch/commit identified;
- current System Registry and host state reviewed;
- existing Teams/Jason production baseline captured;
- MCP service implementation passes deterministic tests;
- MCP service has a defined System Registry entity/lifecycle record;
- supported ChatGPT Business MCP/custom app connection method verified against current OpenAI documentation;
- caller authentication design approved;
- read-only capability allowlist approved;
- provider credentials available only through existing Jason secret boundaries;
- rollback/disable procedure tested locally;
- no action/write tools exposed.

## Phase A — Preserve existing baseline

Capture before changing production exposure:

- `jason-runtime` service health/state;
- `jason-teams-gateway` state and host port ownership;
- OpenClaw state and currently justified functions;
- current System Registry declared/observed/verified status;
- current deployment commit/image identifiers;
- relevant Teams smoke proof.

Do not remove or reconfigure Teams/OpenClaw merely to start the MCP pilot.

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

After second provider is enabled:

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

Pilot may advance only if:

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

Stop pilot expansion if any of the following occur:

- caller identity cannot be established reliably;
- cross-client/tenant scope can be manipulated by the model;
- provider credentials or sensitive secrets reach ChatGPT;
- MCP can bypass Central Orchestrator;
- actions become reachable without explicit authorization/approval design;
- audit/provenance cannot correlate tool execution;
- tool execution becomes dependent on question-specific workflow code;
- ChatGPT Business workspace/app controls are insufficient for the approved risk posture.

## Rollback / disable

The MCP pilot must have a direct disable mechanism independent of provider credential destruction.

Rollback should:

1. disable/unpublish the ChatGPT custom app/MCP connection;
2. stop/disable the Jason MCP service if necessary;
3. leave existing provider connectors and Central Orchestrator intact;
4. leave Teams/OpenClaw baseline unchanged unless separately modified;
5. verify services and production topology after rollback;
6. record the rollback evidence.

## Evidence to preserve

For each pilot milestone preserve:

- repository commit;
- System Registry lifecycle/verification record;
- service health/verification result;
- tool enumeration snapshot without secrets;
- identity-binding proof;
- representative read results/provenance;
- failed-closed tests;
- cost/usage summary;
- ChatGPT pilot findings;
- rollback proof where tested.

## Production promotion

Do not call the ChatGPT/Jason MCP path production until:

- the service is registered in System Registry;
- declared/observed/verified state agrees;
- identity/authority/security proof passes;
- read-only pilot acceptance criteria pass;
- runbook/rollback is current;
- documentation is updated from target architecture to observed operational state.
