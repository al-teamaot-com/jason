# Jason Datto RMM Generalized Governed Component Execution — 2026-09-17

**Classification:** Evidence / production capability proof  
**Status:** Completed  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP ↔ Central Orchestrator ↔ Datto RMM generalized governed component discovery, approval, execution, asynchronous job monitoring, governed StdOut retrieval, and command-level approval classification for the reviewed ad-hoc PowerShell component  
**Authority note:** This record preserves evidence. It grants no new provider, identity, business, endpoint, or execution authority.

## Section Goal

Prove that a technician can name a Datto component and endpoint conversationally, Jason can resolve both from live provider evidence, apply server-controlled approval policy, accept explicit technician approval through the live MCP contract, execute exactly one governed component job, monitor that same job to terminal state, retrieve actual StdOut, and preserve provider/governance boundaries.

A later bounded extension in the same workstream also proves that the exact reviewed Datto PowerShell runner can accept its live `usrInput` variable and that Jason can classify a narrow deterministic set of read-only PowerShell commands for standing-safe execution while keeping mutating, sensitive, ambiguous, or unclassified commands behind explicit per-run approval.

## Current production boundary

- Repository: `al-teamaot-com/jason`
- Branch: `feature/jason-generic-governed-execution-20260915`
- Live MCP source: `d73a87b0c1867eaee90fa0b310893cb62f9b1e9d`
- Live image: `jason-mcp:generic-governed-d73a87b0c186`
- Live container: `jason-mcp-pilot`
- MCP status: `ok`
- MCP mode: `governed-read-plus-actions`
- Phase: `governed-action-pilot`
- Execution coordinator: Central Orchestrator
- Generic governed execution tool: enabled
- `direct_provider_access=false`
- Write tools enabled: true
- Active write capabilities include `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`
- Follow-up Datto read capabilities include `automation.job.read` and `automation.job.output.read`
- Datto approval policy: server-classified `standing_safe` or `per_run`

## Defects removed during this section

The generalized execution path exposed several pilot-era constraints. They were corrected rather than bypassed:

1. **Incomplete Datto component catalog discovery** — Jason previously trusted provider pagination metadata and could stop after the first bounded page. Catalog discovery now enumerates provider pages sequentially to an actual terminal empty page, deduplicates durable UIDs, and fails closed on repeated pages or safety bounds.
2. **Caller target-class mismatch** — caller/model-supplied labels such as `Desktop` versus `Workstation` no longer veto an otherwise exact approved endpoint. Device class is server-controlled metadata; exact endpoint identity remains enforced.
3. **Static component identity collision** — once a component is verified against the complete live Datto catalog, its live UID/name pair is authoritative provider identity. Static configuration contributes approval classification and cannot override a newer live identity. Unknown live-verified components default to `per_run`; live discovery cannot manufacture `standing_safe` authority.
4. **MCP approval transport mismatch** — the live MCP tool exposes `capability` plus `arguments`. Explicit Datto approval now travels as reserved `arguments.explicit_approval=true`, is consumed by Jason before provider execution, and is not forwarded to Datto.
5. **Incomplete job-output follow-up construction** — Datto StdOut retrieval requires the exact job UID, device UID, and component UID. Earlier conversational follow-up reads could supply only the job UID and then surface the downstream failure as `CAPABILITY_INVOCATION_FAILED`, misleading the technician into believing Jason or Datto output retrieval was broken. Component execution results now preserve the exact job/device/component binding and return a ready-to-use `output_read_arguments` bundle. `automation.job.output.read` prevalidates the required selectors before any provider call; incomplete reads are identified as Jason request-construction errors and explicitly instruct the caller to retry the read without redispatching the component.
6. **Variableized component execution gap** — the exact Datto component `Run Ad Hoc Command (PowerShell 2-5) [WIN]` exposes the live string variable `usrInput`, but Jason's execution policy previously permitted no conversation-supplied variables for this component. Jason now recognizes the exact reviewed UID/name pair and permits only `usrInput`, preserving Datto's normal variable structure and failing closed for unknown variables or unreviewed component identities.
7. **Overly coarse PowerShell approval policy** — forcing the entire arbitrary-PowerShell component to `per_run` was safe but prevented useful read-only diagnostics from operating under standing policy. Jason now performs a server-side, fail-closed command classification. A narrow deterministic read-only allowlist may receive standing-safe authority for the exact invocation; mutating, sensitive, multi-command, remote-scope, ambiguous, obfuscated, or unknown commands remain `per_run`. The caller/model cannot self-classify a command as safe.

## Relevant implementation commits

- `a6403496084b6c5d7cb51e524e7208c0ca92adf9` — enumerate complete Datto component catalog;
- `d40ea4158dbff7d08b5bf56492d0b6c6bbad5cf6` — canonicalize Datto target class server side;
- `b08fdb0aa3c635f4c6e2f4febc3c8ad4e8d83f6b` — trust live Datto identity while preserving component policy;
- `900c0c1152bad8d13c5f619f45d6c6cba99dc657` — carry Datto approval through MCP arguments;
- `a94f5a97dfb27c6c0c02a6d40e050b278e3f40a8` — harden Datto job output follow-up contract;
- `13fea2c5bda7a9506cbe85211be53efdd9be5d81` — permit governed Datto ad-hoc PowerShell input;
- `d73a87b0c1867eaee90fa0b310893cb62f9b1e9d` — classify governed PowerShell commands by effect.

## Exact live EDR target and component

Endpoint:

- hostname: `AOT-50282`;
- device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`.

Component:

- `Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024`;
- component UID: `9c30dab8-b76c-417d-a264-b3ca91995179`;
- operation classification: modifying/remediation;
- approval mode: `per_run`;
- optional component variable observed during catalog discovery: `varURLOverride`.

## Explicit approval and exactly one EDR execution

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

The earlier failed StdOut reads were not a provider-output timing failure. They were caused by an incomplete Jason read request that supplied the job UID without the exact device UID and component UID required by the governed Datto output-read path. With all selectors supplied, the same completed job returned StdOut successfully without any second component execution.

Latest successful output-read verification correlation:

- `corr_mcp_823e4a614544450f96db03287008d7d5`.

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

The governed output proves that terminal completion and component-output retrieval both work through Jason for this modifying `per_run` component. The earlier `CAPABILITY_INVOCATION_FAILED` output-read messages are stale and are not authoritative evidence of a Datto failure.

## Hardened job follow-up contract

Production source `a94f5a97dfb27c6c0c02a6d40e050b278e3f40a8` introduced an explicit follow-up contract intended to prevent the same technician-confidence failure from recurring:

- both asynchronously accepted and terminally verified Datto component-execution results preserve `job_uid`, `device_uid`, `component_uid`, and `component_name`;
- the MCP action projection returns `job_read_arguments` for polling and `output_read_arguments` containing the exact job/device/component selector bundle plus the default `stdout` stream;
- the result advertises a follow-up contract of `poll_same_job=true`, `read_output_after_terminal=true`, and `do_not_redispatch=true`;
- `automation.job.output.read` accepts the returned selector bundle directly or canonicalizes equivalent exact selectors;
- a missing job/device/component selector is rejected before the governed provider read with `AUTOMATION_JOB_OUTPUT_SELECTORS_REQUIRED`;
- such a rejection is labeled `failure_domain=request_construction`, `provider_called=false`, and `retryable=true` rather than being presented as a Datto/provider failure;
- invalid output-stream selection is likewise rejected as a request-construction error before provider execution;
- the corrective action is always to repair and retry the read-only request, never to rerun the component.

Deployment acceptance recorded:

- `INCOMPLETE_READ_BLOCKED_BEFORE_PROVIDER=PASS`;
- `MISSING_SELECTORS_NOT_PROVIDER_FAILURE=PASS`;
- `DO_NOT_REDISPATCH_CONTRACT=PASS`;
- `COMPLETE_READ_CANONICALIZED=PASS`;
- `EXECUTION_RETURNS_OUTPUT_SELECTOR_BUNDLE=PASS`;
- `VERIFIED_AND_ASYNC_RESULTS_PRESERVE_BINDING=PASS`;
- `LIVE_SELECTOR_PREFLIGHT=PASS`;
- `LIVE_REQUEST_ERROR_NOT_PROVIDER_ERROR=PASS`;
- `LIVE_OUTPUT_SELECTOR_BUNDLE=PASS`;
- `LIVE_NO_REDISPATCH_CONTRACT=PASS`;
- `DATTO_OUTPUT_FOLLOWUP_HARDENING=PASS`;
- deployment itself executed no Datto component (`DATTO_COMPONENT_EXECUTED=NO`).

## Governed ad-hoc PowerShell variable support

The live Datto catalog identified:

- component: `Run Ad Hoc Command (PowerShell 2-5) [WIN]`;
- component UID: `8a1c153c-feee-41c5-9c9b-58a48e0214fe`;
- description: executes a PowerShell command supplied through `usrInput`;
- variable: `usrInput`;
- type: `string`.

Source `13fea2c5bda7a9506cbe85211be53efdd9be5d81` binds variable permission to that exact reviewed Datto UID/name pair. It allows only `usrInput`, requires it to be present, preserves the supplied string into Datto's normal `jobComponent.variables` structure, rejects unknown variables, and rejects an unreviewed component identity attempting to reuse the same display name.

Acceptance evidence:

- `USRINPUT_ACCEPTED=PASS`;
- `DATTO_VARIABLE_FORMAT=PASS`;
- `UNKNOWN_VARIABLE_FAILS_CLOSED=PASS`;
- `UNREVIEWED_IDENTITY_FAILS_CLOSED=PASS`;
- `ARBITRARY_POWERSHELL_ALWAYS_PER_RUN=PASS` at that intermediate source boundary;
- deployment executed no provider mutation (`PROVIDER_MUTATION=NO`, `DATTO_COMPONENT_EXECUTED=NO`).

## Command-level PowerShell approval policy

Source `d73a87b0c1867eaee90fa0b310893cb62f9b1e9d` replaces the coarse intermediate rule that made every ad-hoc PowerShell invocation `per_run` with a narrower server-derived effect classification.

The policy is deliberately conservative:

- only the exact reviewed PowerShell component can use command-level classification;
- the caller/model cannot submit or override its own safety classification;
- a narrow deterministic allowlist of operational read cmdlets can receive standing-safe authority;
- only simple one-line pipelines composed of a reviewed primary read cmdlet and reviewed non-mutating pipeline transforms qualify;
- mutating commands such as `Start-Service`, `Stop-Service`, `Restart-Service`, or `Set-*` require per-run approval;
- semicolon/multi-command chains, script blocks, variable expansion, method/expression indirection, redirection, encoded/obfuscated execution, native executable launches, remote-scope widening, and unknown cmdlets fall back to per-run approval;
- generic file-content, registry, CIM/WMI, and other potentially sensitive reads are intentionally not standing-safe in this first policy even when technically non-mutating;
- a command that cannot be proven safe is approval-required rather than guessed safe.

Examples accepted as standing-safe by the tested policy include `Get-Date`, `Get-Service`, `Get-NetIPConfiguration`, `Get-MpComputerStatus`, selected network/status cmdlets, and reviewed formatting/filtering pipeline stages.

Examples that remain per-run include service changes, `Get-Content`, registry reads, CIM/WMI queries, chained commands, remoting to another managed computer, `Invoke-Expression`, redirection, and encoded/native shell execution.

Deployment acceptance:

- `READ_ONLY_COMMANDS_STANDING_SAFE=PASS`;
- `MUTATING_AMBIGUOUS_SENSITIVE_PER_RUN=PASS`;
- `MCP_READ_ONLY_NO_TECH_APPROVAL=PASS`;
- `MCP_MUTATING_REQUIRES_APPROVAL=PASS`;
- `MCP_MUTATING_WITH_APPROVAL=PASS`;
- `LIVE_READ_ONLY_COMMAND_CLASSIFICATION=PASS`;
- `LIVE_MUTATING_COMMAND_REQUIRES_APPROVAL=PASS`;
- `LIVE_SERVER_DERIVED_CLASSIFICATION=PASS`;
- `DATTO_POWERSHELL_COMMAND_POLICY=PASS`;
- deployment executed no endpoint command (`DATTO_COMPONENT_EXECUTED=NO`).

This establishes policy behavior in the real production image. A separate live acceptance execution of a harmless read-only one-liner remains appropriate if an operational proof of actual Datto dispatch/StdOut under the new standing-safe command policy is desired.

## Governance invariants preserved

- `direct_provider_access=false` remains mandatory.
- Central Orchestrator remains authoritative for execution.
- Provider credentials are not exposed to ChatGPT.
- Exact endpoint identity remains required by the current execution scope.
- Component identity comes from governed live catalog resolution.
- Safety/approval classification remains server-controlled.
- A reviewed PowerShell invocation may receive standing-safe treatment only when the exact server classifier deterministically proves the command is within the narrow read-only policy.
- Mutating, disruptive, sensitive, ambiguous, unknown, or unclassified PowerShell commands remain `per_run`.
- Caller/model-supplied approval classification cannot widen authority.
- Explicit approval applies to the exact execution only.
- Exactly one dispatch is followed by monitoring of the same job ID.
- Active, incomplete, or incorrectly constructed output reads are not permission to dispatch again.
- Historical success never becomes authority for a future modifying action; any Resolution Memory capability remains subordinate to normal Jason authority and approval policy.

## Operational monitoring cadence

ChatGPT's standard recurring automation scheduler is not a sub-hour polling engine. During an active conversation, a technician can ask ChatGPT to check the job at any time and Jason can immediately perform another read-only `automation.job.read`.

For unattended 5- or 10-minute polling, the durable implementation should be inside Jason or another approved operational scheduler. A Jason-side watcher should retain the exact job UID and its device/component binding, perform bounded read-only polling, stop automatically at terminal state or timeout, retrieve output once terminal using the preserved selector bundle, and notify the technician without creating a second provider mutation.

## Operational learning follow-on

A separate planned roadmap item, `TODO-OPS-001 — Operational Resolution Memory and case-based troubleshooting reuse`, now captures the requirement for Jason to learn from recurring alerts/tickets and prior governed outcomes. It is subordinate to `REFLECT-001` and must reuse successful and failed historical evidence without creating a parallel authority system or silently generalizing client-specific exceptions.

## Section Goal status — CLOSED

Final acceptance:

1. complete live component catalog discovery — **proven**;
2. exact endpoint resolution — **proven**;
3. exact live component resolution — **proven**;
4. static policy no longer overrides live provider identity — **proven**;
5. server-controlled target class — **proven**;
6. explicit conversational approval transported through the live MCP contract — **proven**;
7. exactly one governed Datto EDR job created — **proven**;
8. durable job UID returned — **proven**;
9. repeated read-only polling of the same job — **proven**;
10. terminal completion — **proven (`completed`)**;
11. final governed StdOut retrieval with exact job/device/component selectors — **proven**;
12. root cause of earlier StdOut failures identified as incomplete request construction rather than provider failure — **proven**;
13. component execution returns the exact selector bundle required for subsequent output retrieval — **proven**;
14. incomplete output reads fail before provider invocation with an actionable non-provider error — **proven**;
15. no-redispatch follow-up behavior is encoded and regression-tested — **proven**;
16. exact reviewed ad-hoc PowerShell component accepts only its approved `usrInput` variable — **proven**;
17. Datto quick-job variable construction for `usrInput` — **proven in the built/runtime policy test**;
18. unknown or unreviewed PowerShell variable identities fail closed — **proven**;
19. narrow deterministic read-only PowerShell commands receive standing-safe policy without technician per-run approval — **proven in MCP/runtime policy tests**;
20. mutating, sensitive, ambiguous, remote-scope, and unknown PowerShell commands remain explicit per-run approval — **proven in MCP/runtime policy tests**;
21. caller/model cannot self-classify a PowerShell command as safe — **proven**;
22. production MCP remains healthy in governed-read-plus-actions mode with Central Orchestrator authority and `direct_provider_access=false` — **verified**;
23. production deployment of these policy changes executed no endpoint command — **proven by deployment evidence**;
24. Operational Resolution Memory requirement captured in the governed backlog and linked to REFLECT-001 — **complete**;
25. documentation reconciliation — **complete for this proof boundary**.

Grafana/Prometheus release reconciliation remains separate operational observability work and must use the actual deployed MCP image/source as its expected boundary. No observability state is claimed here without fresh monitoring evidence.
