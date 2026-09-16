# Jason Datto RMM Cross-Chat Governed Execution / Output Proof — 2026-09-16

**Classification:** Evidence / bounded production proof  
**Status:** Completed  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP ↔ Central Orchestrator ↔ Datto RMM governed component execution and output retrieval  
**Authority note:** This record preserves evidence. It grants no new provider, identity, business, or execution authority.

## Section Goal

Prove the complete cross-chat governed Datto component workflow without reusing prior execution approval: resolve the exact endpoint and component, obtain fresh explicit per-execution approval, execute exactly one safe diagnostic component, verify the resulting Datto job reaches terminal completion, retrieve actual component StdOut through Jason's governed read path, and reconcile durable project/monitoring state.

## Current live boundary used

- Repository: `al-teamaot-com/jason`
- Branch: `feature/jason-generic-governed-execution-20260915`
- Live source commit: `e9c7a76318aa12b150194875726b1ba54bf6d61b`
- Commit message: `Accept bounded JSON arrays from provider reads`
- Live MCP image: `jason-mcp:generic-governed-e9c7a76318aa`
- Live MCP container: `jason-mcp-pilot`
- MCP mode: `governed-read-plus-actions`
- Execution coordinator: Central Orchestrator
- Generic governed execution tool: enabled
- `direct_provider_access=false`
- Action authority: exact Jason grant plus per-execution approval

The MCP status and capability catalog were freshly reloaded before the mutation. `automation.component.execute`, `automation.job.read`, and `automation.job.output.read` were active. No provider identity, allowlist, grant, or execution scope was broadened.

## Exact pre-read resolution

Governed `endpoint.device.search` resolved exactly one target:

- Endpoint: `AOT-50282`
- Device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`
- Site: `Atlantic Office Machines`
- Site UID: `9bb56523-cade-4ffb-bc34-696e788f0f4c`
- Resolution correlation: `corr_mcp_e6206254c5fd495e8ebbe7b0e2131f8a`

Governed `automation.component.search` resolved exactly one component:

- Component: `Get-DNS Settings AOT Ver 06042025-1`
- Component UID: `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`
- Variables: none
- Resolution correlation: `corr_mcp_9aef3c62b71a4352b5ce2ec37908a615`

## Fresh approval boundary

The prior proof approval was treated as consumed and was not reused. The AOT Owner then explicitly approved one new execution of `Get-DNS Settings AOT Ver 06042025-1` on `AOT-50282`.

The approved scope was one non-disruptive diagnostic execution, no variables, one provider mutation, one attempt, and no retry.

## Exactly one governed execution

Jason invoked `automation.component.execute` exactly once through the generic governed action surface with only the exact device UID, component UID, and an empty variable map.

Result:

- Provider: `datto_rmm_component_execution`
- Provider attempts: `1`
- Result status: `accepted`
- Immediate job status: `active`
- Readback verified: `true`
- Completion verified at action return: `false` because the Datto job was asynchronous
- Allowlist: `AOT governed diagnostic pilot`
- Durable Datto job UID: `741a2d02-587d-4348-9f26-b4982d337732`
- Action correlation ID: `corr_mcp_action_d49b19600e6f4c50a60f43892af66458`

No retry or second provider mutation occurred.

## Terminal completion through governed reads only

Jason then used only `automation.job.read` against the exact returned job UID. The job remained `active` during intermediate reads and later reached terminal status:

- Job UID: `741a2d02-587d-4348-9f26-b4982d337732`
- Job name: `Jason - Get-DNS Settings AOT Ver 06042025-1`
- Terminal status: `completed`
- Final terminal-read correlation: `corr_mcp_12eafe5022dc42cb8a42091be669d8cf`

No mutation was issued while polling.

## Actual governed StdOut retrieval

After terminal completion, Jason called `automation.job.output.read` with the exact:

- job UID `741a2d02-587d-4348-9f26-b4982d337732`;
- device UID `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- stream `stdout`.

The governed read succeeded with correlation `corr_mcp_2c624f2cda234afab3be73b70906e8b0`, `match_count=1`, `truncated=false`, and the actual component output below:

```text
====================================================
Interface Alias     : ZeroTier One [60ee7c034a983def]
Interface Description: ZeroTier Virtual Port
MAC Address         :
DHCP Enabled (IPv4) : Disabled
IPv4 Address        : 192.168.193.90
Default Gateway     : 25.255.255.254
DNS Servers         : fec0:0:0:ffff::1, fec0:0:0:ffff::2, fec0:0:0:ffff::3
====================================================

====================================================
Interface Alias     : ZeroTier One [b103a835d22e664a]
Interface Description: ZeroTier Virtual Port #2
MAC Address         :
DHCP Enabled (IPv4) : Disabled
IPv4 Address        : 10.148.127.90
Default Gateway     : 25.255.255.254
DNS Servers         : fec0:0:0:ffff::1, fec0:0:0:ffff::2, fec0:0:0:ffff::3
====================================================

====================================================
Interface Alias     : vEthernet (NDA-External-VS)
Interface Description: Hyper-V Virtual Ethernet Adapter #2
MAC Address         : F0-2F-74-84-1F-34
DHCP Enabled (IPv4) : Disabled
IPv4 Address        : 192.168.12.33
Default Gateway     : 192.168.12.1
DNS Servers         : 103.247.36.36, 103.247.37.37, 8.8.8.8
====================================================

====================================================
Interface Alias     : vEthernet (Default Switch)
Interface Description: Hyper-V Virtual Ethernet Adapter
MAC Address         : 00-15-5D-DC-DD-50
DHCP Enabled (IPv4) : Disabled
IPv4 Address        : 172.23.176.1
DNS Servers         : fec0:0:0:ffff::1, fec0:0:0:ffff::2, fec0:0:0:ffff::3
====================================================
```

The operator-provided Datto RMM screenshot independently showed the same `AOT-50282` job as successful and displayed matching output. The screenshot is corroborating evidence; the governed Jason read path remains the authoritative machine-readable proof for this workflow.

## Transport regression closure

The output read exercises the provider endpoint that returns a JSON array. The successful live retrieval on source `e9c7a763...` demonstrates that the bounded JSON-array transport fix is active in the production MCP path and that the prior `PROVIDER_TRANSPORT_FAILURE` condition is not present in this proof.

## Governance invariants preserved

- `direct_provider_access=false` remained intact.
- Central Orchestrator remained authoritative.
- Exact Jason grants and fresh per-execution approval remained required.
- The prior approval was not reused.
- Exactly one provider mutation and one provider attempt occurred.
- No retry or broader-credential fallback occurred.
- No arbitrary shell/script text was exposed as an execution interface.
- No reboot, shutdown, forced logoff, process termination, network/VPN interruption, or interruptive service restart occurred.
- Provider credentials were not exposed to ChatGPT.

## Grafana / Prometheus reconciliation and acceptance

The existing repository-provisioned `Jason Governed Actions` dashboard and `jason_datto_governed_execution_contract` remained the authoritative observability surface. Because the MCP had advanced from the earlier `8f1e864...` release to `e9c7a763...`, the production-health unit was updated to expect the exact current image/source without changing MCP runtime or provider authority:

- `JASON_EXPECTED_MCP_IMAGE=jason-mcp:generic-governed-e9c7a76318aa`
- `JASON_EXPECTED_MCP_SOURCE_REVISION=e9c7a76318aa12b150194875726b1ba54bf6d61b`

The clean deployment worktree was fast-forwarded to monitoring/documentation head `b2f8b0e740d8e61ee8d3d2e9f84ff13bdbef3752` and the existing rollback-protected monitoring-only deployment was run from that worktree.

Deployment acceptance returned:

- `PRECHECK=PASS`
- `SOURCE_VALIDATION=PASS`
- `PRODUCTION_HEALTH_EXPORTER=PASS`
- `MONITORING_CONTAINERS=PASS`
- `CORE_ISOLATION=PASS`
- `PROMETHEUS_PRODUCTION_HEALTH=UP`
- `PROMETHEUS_PRODUCTION_RULES=PASS`
- `GRAFANA_PRODUCTION_HEALTH_DASHBOARD=PASS`
- `METRIC_CONTRACT=PASS`
- `RUNTIME_CHANGED=NO`
- `MCP_CHANGED=NO`
- `OPENBAO_CHANGED=NO`
- `PROVIDER_ACCESS=NO`
- `PROVIDER_WRITES=NO`

Rollback evidence directory: `/tmp/jason-production-health-rollback-20260916T151911Z`.

A final read-only live verification returned `1` for all current Datto/MCP contract checks:

- `jason_mcp_contract{check="datto_execution_profile"} 1`
- `jason_mcp_contract{check="datto_execution_scope"} 1`
- `jason_mcp_contract{check="image"} 1`
- `jason_mcp_contract{check="source_revision"} 1`
- `jason_datto_governed_execution_contract 1`

Grafana also returned:

- dashboard UID: `jason-governed-actions`
- dashboard title: `Jason Governed Actions`

The monitoring deployment and final verification were observational only. No provider call, provider mutation, MCP recreation, OpenBao change, or authority expansion occurred.

## Section Goal closure

The Section Goal is **complete**:

1. exact endpoint resolution — **proven**;
2. exact component resolution — **proven**;
3. fresh explicit per-execution approval — **proven and consumed**;
4. exactly one governed diagnostic execution — **proven**;
5. durable Datto job UID returned — **proven**;
6. terminal completion through governed read-only polling — **proven (`completed`)**;
7. actual StdOut through `automation.job.output.read` — **proven**;
8. cross-chat continuity without reusing prior approval — **proven**;
9. bounded JSON-array provider transport — **live-proven**;
10. governance boundaries — **preserved**;
11. durable current-state/proof documentation — **reconciled**;
12. Grafana/Prometheus current-release observability — **live and passing**.

This completed proof does not authorize arbitrary Datto execution or any disruptive action. Future execution still requires the active bounded capability, exact Jason grants, provider containment, and fresh per-execution approval. Disruptive operations continue to require explicit technician approval for that exact disruptive action.
