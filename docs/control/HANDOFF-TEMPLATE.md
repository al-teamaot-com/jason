# Project Jason Workstream Handoff — <Name>

**Date:** YYYY-MM-DD  
**Status:** Active | Blocked | Ready for review | Complete  
**Owner / operator:** <person or role>  
**Repository branch / PR:** <branch / PR or None>  
**Governing records:** <links>  
**Related System Registry entities:** <IDs or None>

## Objective

State the exact outcome this workstream is trying to achieve.

## Last durable success

Describe the last step that is supported by committed code/documentation or durable evidence.

Do not use conversational memory as proof.

## Repository state

Record only durable repository facts needed to resume:

- branch / PR;
- relevant commit or merge point when materially important;
- unmerged dependencies;
- CI status if it affects the next action.

Do not claim a repository SHA is still current without checking GitHub or the repository.

## Intended state

Summarize what the governing architecture/specification says should exist.

Link to the authoritative records rather than reproducing them.

## Observed / verified runtime state

State only what has current evidence.

For operational topology, reference the System Registry, lifecycle history, verification report, and applicable proof record.

If the physical Jason host has not been inspected recently, say so explicitly.

## Work completed

- <bounded completed item>
- <bounded completed item>

## Unresolved blockers / uncertainty

- <blocker or unknown>
- <what evidence is needed to resolve it>

Distinguish a known defect from an inference.

## Next safe actions

1. <next bounded action>
2. <next bounded action>
3. <next bounded action>

Mark any action that requires the physical Jason host, production credentials, live provider access, approval, or consequential execution.

## Do not do

List actions that must not be taken casually, such as:

- silent remediation of System Registry drift;
- bypassing Central Orchestrator;
- weakening identity/authority gates;
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

List canonical documents updated by the workstream and any documentation still required before the work can be considered complete.

## Resume instructions for a future session

A future session should:

1. Read `docs/index.md`.
2. Read `docs/control/CURRENT.md`.
3. Read this handoff.
4. Read the governing architecture/ADR/runbook records linked above.
5. Inspect current GitHub state before repository writes.
6. Inspect current System Registry/host evidence before asserting production state.
7. Continue only from evidence-supported state.
