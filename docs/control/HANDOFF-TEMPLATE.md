# Project Jason Workstream Handoff — <Name>

**Date:** YYYY-MM-DD  
**Status:** Active | Blocked | Ready for review | Complete  
**Owner / operator:** <person or role>  
**Repository branch / PR:** <branch / PR or None>  
**Governing records:** <links>  
**Related System Registry entities:** <IDs or None>

## Objective

State the exact outcome this workstream is trying to achieve.

## Component / extension classification

Identify the affected Jason component class (provider/connector, capability/resource, agent/reasoning component, governance/policy gate, ingress/interface, identity/authority, secret integration, internal service, System Registry entity, evidence/audit component, deployment/operations, or other).

Link to the applicable path in `docs/control/EXTENSION-CONSTRUCTION-MAP.md` and identify the closest governed reusable implementation pattern.

If no sufficient construction path exists, record that as a documentation defect rather than leaving the next session to rediscover it.

## Last durable success

Describe the last step supported by committed code/documentation or durable evidence. Do not use conversational memory as proof.

## Repository state

Record only durable repository facts needed to resume: branch/PR, relevant commit/merge point when materially important, unmerged dependencies, and CI status if it affects the next action.

Do not claim a repository SHA is still current without checking GitHub/repository state.

## Intended state

Summarize what governing architecture/specification says should exist. Link to authoritative records rather than reproducing them.

## Observed / verified runtime state

State only what has current evidence.

For operational topology, reference System Registry, lifecycle history, verification report, and applicable proof record. If the physical Jason host has not been inspected recently, say so explicitly.

## Work completed

- <bounded completed item>
- <bounded completed item>

## Unresolved blockers / uncertainty

- <blocker or unknown>
- <evidence needed to resolve it>

Distinguish known defects from inference.

## Next safe actions

1. <next bounded action>
2. <next bounded action>
3. <next bounded action>

Mark actions requiring physical Jason host, production credentials, live provider access, approval, or consequential execution.

## Do not do

List actions that must not be taken casually, including:

- rediscovering documented fundamentals from chat/code instead of reading canonical sources;
- silent remediation of System Registry drift;
- bypassing Central Orchestrator;
- weakening identity/authority/policy/approval gates;
- allowing agents/connectors to communicate around governed orchestration;
- copying secrets into logs/evidence/chat;
- assuming a prior deployment is still current;
- promoting lifecycle state without registered proof.

## Evidence and records

| Evidence / record | What it proves | Location / reference |
|---|---|---|
| <record> | <claim> | <path/reference> |

## Security / data-handling notes

Identify relevant secret handling, client isolation, credential references, evidence restrictions, or privacy constraints.

## Documentation impact

Explicitly state impact for:

- governing architecture/standard/ADR;
- component/capability/provider contract;
- reusable construction guidance / Extension Construction Map;
- System Registry;
- operations/runbooks;
- proof/session evidence;
- `docs/control/CURRENT.md`.

`No documentation impact` must be an explicit reviewed conclusion, not an omission.

## Resume instructions for a future session

A future session should:

1. Read `docs/index.md`.
2. Read `docs/control/JASON-FUNDAMENTALS.md`.
3. Read `docs/control/CURRENT.md`.
4. Read `docs/control/EXTENSION-CONSTRUCTION-MAP.md` for the affected component class.
5. Read this handoff.
6. Read governing architecture/ADR/component/standard/runbook/construction records linked above.
7. Inspect current GitHub state before repository writes.
8. Inspect current System Registry/host evidence before asserting production state.
9. Continue only from evidence-supported state.
