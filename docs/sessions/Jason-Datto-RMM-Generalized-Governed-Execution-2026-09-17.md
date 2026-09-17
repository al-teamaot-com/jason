# Jason Datto RMM Generalized Governed Component Execution — 2026-09-17

**Classification:** Evidence / production capability proof in progress  
**Status:** Execution accepted; terminal completion and StdOut pending  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP ↔ Central Orchestrator ↔ Datto RMM generalized governed component discovery, approval, execution, and asynchronous job monitoring  
**Authority note:** This record preserves evidence. It grants no new provider, identity, business, or execution authority.

## Section Goal

Prove that a technician can name a Datto component and endpoint conversationally, Jason can resolve both from live provider evidence, apply server-controlled approval policy, accept explicit technician approval through the live MCP contract, execute exactly one governed component job, monitor that same job to terminal state, retrieve actual StdOut, and preserve provider/governance boundaries.

## Production boundary

- Repository: `al-teamaot-com/jason`
- Branch: `feature/jason-generic-governed-execution-20260915`
- Live MCP source: `900c0c1152bad8d13c5f619f45d6c6cba99dc657`
- Live image: `jason-mcp:generic-governed-900c0c1152ba`
- Live container: `jason-mcp-pilot`
- MCP mode: `governed-read-plus-actions`
- Execution coordinator: Central Orchestrator
- Generic governed execution tool: enabled
- `direct_provider_access=false`
- Active Datto action capability: `automation.component.execute`
- Follow-up read capabilities: `automation.job.read`, `automation.job.output.read`
- Approval policy: server-classified `standing_safe` or `per_run`

## Defects removed during this section

The generalized execution path exposed several pilot-era constraints. They were corrected rather than bypassed:

1. **Incomplete Datto component catalog discovery** — Jason previously trusted provider pagination metadata and could stop after the first bounded page. Catalog discovery now enumerates provider pages sequentially to an actual terminal empty page, deduplicates durable UIDs, and fails closed on repeated pages or safety bounds.
2. **Caller target-class mismatch** — caller/model-supplied labels such as `Desktop` versus `Workstation` no longer veto an otherwise exact approved endpoint. Device class is server-controlled metadata; exact endpoint identity remains enforced.
3. **Static component identity collision** — once a component is verified against the complete live Datto catalog, its live UID/name pair is authoritative provider identity. Static configuration contributes approval classification and cannot override a newer live identity. Unknown live-verified components default to `per_run`; live discovery cannot manufacture `standing_safe` authority.
4. **MCP approval transport mismatch** — the live MCP tool exposes `capability` plus `arguments`. Explicit Datto approval now travels as reserved `arguments.explicit_approval=true`, is consumed by Jason before provider execution, and is not forwarded to Datto.

Relevant implementation commits:

- `a6403496084b6c5d7cb51e524e7208c0ca92adf9` — enumerate complete Datto component catalog;
- `d40ea4158dbff7d08b5bf56492d0b6c6bbad5cf6` — canonicalize Datto target class server side;
- `b08fdb0aa3c635f4c6e2f4febc3c8ad4e8d83f6b` — trust live Datto identity while preserving component policy;
- `900c0c1152bad8d13c5f619f45d6c6cba99dc657` — carry Datto approval through MCP arguments.

## Exact live target and component

Endpoint:

- hostname: `AOT-50282`;
- device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`.

Component:

- `Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024`;
- component UID: `9c30dab8-b76c-417d-a264-b3ca91995179`;
- operation classification: modifying/remediation;
- approval mode: `per_run`;
- optional component variable observed during catalog discovery: `varURLOverride`.

## Explicit approval and exactly one execution

The AOT Owner explicitly approved execution of the exact component on the exact endpoint. Jason accepted the approval through `arguments.explicit_approval=true` and created one Datto job.

Datto job:

- job UID: `77bbc834-097d-49a2-95ce-0066559f73d5`;
- component: `Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024`;
- endpoint: `AOT-50282`;
- provider state after acceptance: `active`.

No duplicate component execution should be issued while this durable job is active. Follow-up work must use read-only job status checks against this exact job UID.

## Asynchronous monitoring evidence

Jason has already used `automation.job.read` against the exact job UID and received `status=active`. Repeated status reads are safe because they do not create another provider mutation.

Current known state at documentation time:

- execution accepted by Datto: **yes**;
- job created: **yes**;
- job UID durable and readable: **yes**;
- current status: **active**;
- second provider mutation: **not issued**;
- terminal completion: **pending**;
- final governed StdOut: **pending**.

When terminal state is reached, use `automation.job.output.read` with the exact job UID, exact device UID, exact component UID, and `stream=stdout`. Record the terminal state and output in this document before closing the Section Goal.

## Governance invariants preserved

- `direct_provider_access=false` remains mandatory.
- Central Orchestrator remains authoritative for execution.
- Provider credentials are not exposed to ChatGPT.
- Exact endpoint identity remains required.
- Component identity must come from governed live catalog resolution.
- Safety/approval classification remains server-controlled.
- `standing_safe` may execute under standing policy only when explicitly classified server-side.
- Modifying, disruptive, destructive, unknown, or unclassified live components remain `per_run` unless separately classified by trusted policy.
- Caller/model-supplied approval classification cannot widen authority.
- Explicit approval applies to the exact execution only.
- One dispatch is followed by monitoring of the same job ID; active status is not a reason to dispatch again.

## Operational monitoring cadence

ChatGPT's standard recurring automation scheduler is not a sub-hour polling engine. For a long-running Datto job, technicians may ask ChatGPT to check the status at any time and Jason can perform an immediate read-only `automation.job.read`.

For unattended 5- or 10-minute polling, the durable implementation should be inside Jason or another approved operational scheduler, not by repeatedly redispatching the component and not by relying on ChatGPT recurring automations. A Jason-side watcher should store the exact job UID, perform read-only status checks on a bounded interval, stop automatically at terminal state or timeout, retrieve output once terminal, and notify the technician without creating a second provider mutation.

## Section Goal status

Current acceptance:

1. complete live component catalog discovery — **proven**;
2. exact endpoint resolution — **proven**;
3. exact live component resolution — **proven**;
4. static policy no longer overrides live provider identity — **proven**;
5. server-controlled target class — **proven**;
6. explicit conversational approval transported through the live MCP contract — **proven**;
7. exactly one governed Datto job created — **proven**;
8. durable job UID returned — **proven**;
9. repeated read-only polling of the same job — **proven while active**;
10. terminal completion — **pending**;
11. final governed StdOut retrieval — **pending**;
12. final documentation/Grafana reconciliation — **pending until terminal evidence is available**.

The Section Goal remains open only for terminal job evidence, final StdOut interpretation, and final observability/documentation reconciliation. The generalized discovery, approval, and dispatch path itself is live-proven.
