# Jason Datto RMM Generalized Governed Component Execution — 2026-09-17

**Classification:** Evidence / production capability proof  
**Status:** Completed  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP ↔ Central Orchestrator ↔ Datto RMM generalized governed component discovery, approval, execution, asynchronous job monitoring, and governed StdOut retrieval  
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
- provider state after acceptance: `active`;
- terminal state: `completed`.

No duplicate component execution was issued. Follow-up work used read-only job status checks against this exact durable job UID.

## Asynchronous monitoring and terminal evidence

Jason repeatedly used `automation.job.read` against the exact job UID. Intermediate reads returned `status=active`; a later governed read returned terminal `status=completed`.

Terminal governed job-read correlation:

- `corr_mcp_52f7e97ff1824bbba9e3599258`.

The terminal read confirmed:

- job UID: `77bbc834-097d-49a2-95ce-0066559f73d5`;
- job name: `Jason - Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024`;
- terminal status: `completed`;
- discovery complete: `true`.

Repeated status reads were read-only and did not create another provider mutation.

## Governed StdOut retrieval

An earlier attempt to retrieve StdOut failed through the Jason/Datto read path immediately after completion. A later governed retry against the same immutable job identity succeeded without re-running the component.

Successful output-read correlation:

- `corr_mcp_d23517160780446cab8058391b5ec0c5`.

The successful `automation.job.output.read` was bound to the exact:

- job UID `77bbc834-097d-49a2-95ce-0066559f73d5`;
- device UID `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- component UID `9c30dab8-b76c-417d-a264-b3ca91995179`;
- stream `stdout`.

Result:

- output matches: `1`;
- truncated: `false`;
- discovery complete: `true`.

Key returned component output:

- current Datto EDR version reported as `3.17.1.6224`;
- latest Datto EDR installer downloaded successfully;
- installer digital-signature verification passed;
- override/provisioning tenant detected as `https://teamao2154.infocyte.com/`;
- Datto AV reported as already installed and installed properly;
- existing Datto EDR installation detected and overwritten;
- `HUNTAgent` was stopped, deleted, and the old EDR installation removed;
- the replacement RTS/EDR agent was installed to `C:\ProgramData\CentraStage\AEMAgent\RMM.AdvancedThreatDetection\agent.exe`.

The governed output proves that terminal completion and component-output retrieval both work through Jason for this modifying `per_run` component. The temporary output-read failure did not require or justify a second component execution.

## Governance invariants preserved

- `direct_provider_access=false` remained mandatory.
- Central Orchestrator remained authoritative for execution.
- Provider credentials were not exposed to ChatGPT.
- Exact endpoint identity remained required.
- Component identity came from governed live catalog resolution.
- Safety/approval classification remained server-controlled.
- `standing_safe` may execute under standing policy only when explicitly classified server-side.
- Modifying, disruptive, destructive, unknown, or unclassified live components remain `per_run` unless separately classified by trusted policy.
- Caller/model-supplied approval classification cannot widen authority.
- Explicit approval applied to the exact execution only.
- Exactly one dispatch was followed by monitoring of the same job ID.
- Active or temporarily unreadable output was not treated as permission to dispatch again.

## Operational monitoring cadence

ChatGPT's standard recurring automation scheduler is not a sub-hour polling engine. During an active conversation, a technician can ask ChatGPT to check the job at any time and Jason can immediately perform another read-only `automation.job.read`.

For unattended 5- or 10-minute polling, the durable implementation should be inside Jason or another approved operational scheduler. A Jason-side watcher should retain the exact job UID, perform bounded read-only polling, stop automatically at terminal state or timeout, retrieve output once terminal, and notify the technician without creating a second provider mutation.

## Section Goal status — CLOSED

Final acceptance:

1. complete live component catalog discovery — **proven**;
2. exact endpoint resolution — **proven**;
3. exact live component resolution — **proven**;
4. static policy no longer overrides live provider identity — **proven**;
5. server-controlled target class — **proven**;
6. explicit conversational approval transported through the live MCP contract — **proven**;
7. exactly one governed Datto job created — **proven**;
8. durable job UID returned — **proven**;
9. repeated read-only polling of the same job — **proven**;
10. terminal completion — **proven (`completed`)**;
11. final governed StdOut retrieval — **proven**;
12. temporary post-completion output-read failure recovered by read-only retry without duplicate execution — **proven**;
13. documentation reconciliation — **complete for this proof**.

Grafana/Prometheus release reconciliation is operational observability work separate from this evidence record and must use the actual deployed MCP image/source as its expected boundary. No observability state is claimed here without fresh monitoring evidence.
