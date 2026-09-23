# Jason Datto RMM Governed Execution Proof — 2026-09-16

**Classification:** Evidence / bounded production proof  
**Status:** Completed  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP ↔ Central Orchestrator ↔ Datto RMM governed component execution  
**Authority note:** This record preserves evidence. It does not grant new provider, identity, business, or execution authority.

## Goal

Prove the governed Datto RMM execution path end-to-end without weakening governance: confirm reads, execute one safe bounded diagnostic component against the controlled endpoint only after explicit per-execution approval, capture a durable provider job reference, verify terminal completion through the governed read path, reconcile current operational documentation, and expose the accepted bounded state in Grafana/Prometheus without granting new execution authority.

## Controlled target

- Endpoint: `AOT-50282`
- Datto device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`
- Site: `Atlantic Office Machines`
- Site UID: `9bb56523-cade-4ffb-bc34-696e788f0f4c`
- Component: `Get-DNS Settings AOT Ver 06042025-1`
- Component UID: `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`
- Allowlist: `AOT governed diagnostic pilot`
- Variables: none
- Reboot/disruptive action: none

## Live MCP deployment used for final proof

- Source branch: `feature/jason-generic-governed-execution-20260915`
- Source commit: `8f1e864947a2e6e79bf47d3de14daacde7d73144`
- Commit message: `Expose governed Datto job reference for readback`
- Live image tag: `jason-mcp:generic-governed-8f1e864947a2`
- Live image ID: `sha256:d709ca54b66d41e22bd1f67782cd5f6d681c4337bffb359b632523762a27788a`
- Previous live image preserved as rollback: `jason-mcp:generic-governed-4bb3c5dbb0fa`

The MCP self-report after deployment remained:

- `status=ok`
- `mode=governed-read-plus-actions`
- `governed_execution=central-orchestrator`
- `generic_execution_tool=true`
- `direct_provider_access=false`
- write authority `jason_exact_grant_plus_per_execution_approval`
- active write capabilities remained exactly `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`.

## Harmless governed read smoke

A governed `endpoint.device.search` after deployment resolved exactly one `AOT-50282` match to the expected Datto UID before the final mutation proof. This established that the governed read path remained healthy after the MCP replacement.

## Final explicitly approved execution

The AOT Owner explicitly approved one execution of `Get-DNS Settings AOT Ver 06042025-1` on `AOT-50282`.

Jason executed `automation.component.execute` through the generic governed action surface with the exact configured allowlist/endpoint scope and no variables.

Result:

- capability: `automation.component.execute`
- provider: `datto_rmm_component_execution`
- execution status: `succeeded`
- provider job state at immediate readback: `active`
- provider attempts: `1`
- immediate readback verified: `true`
- completion verified at action-return time: `false` because the provider job was asynchronous
- durable job UID: `422d680b-a5ce-4473-b8e8-5d682ec85682`
- action correlation ID: `corr_mcp_action_a1405f1b1c604ab7b92c88032c02ed1b`

The action path therefore behaved as designed: one provider mutation, no retry, accepted asynchronous job, durable job reference returned to the governed client, and no false failure merely because the quick job had not yet reached a terminal state.

## Governed terminal verification

Jason then used the read-only `automation.job.read` capability with the exact returned job UID. No further provider mutation occurred.

The job initially remained `active`, then later returned:

- job UID: `422d680b-a5ce-4473-b8e8-5d682ec85682`
- job name: `Jason - Get-DNS Settings AOT Ver 06042025-1`
- terminal status: `completed`
- final governed read correlation ID: `corr_mcp_25120cdec51d4dbaa837bb6f9bb43b60`

This terminal read completed through provider `datto_rmm` / governed provider capability `datto_rmm.job.read`.

## Conclusion

The bounded Datto RMM governed execution path is now **live-proven end-to-end** for the controlled diagnostic pilot:

1. governed endpoint/component resolution works;
2. explicit per-execution approval is enforced;
3. the separate Datto execution path creates exactly one provider quick job;
4. the provider job UID is returned as bounded governed evidence without exposing raw provider payloads;
5. asynchronous acceptance is represented as `accepted` rather than misclassified as failure;
6. terminal completion is independently verified through `automation.job.read`;
7. `direct_provider_access=false` remained intact;
8. Central Orchestrator remained authoritative;
9. no arbitrary shell text or disruptive action was used;
10. no provider retry or broader-identity fallback occurred.

This proof does **not** authorize arbitrary Datto RMM execution. Production authority remains bounded by Jason capability activation, exact grants, configured allowlists/targets, separate provider execution identity, and per-execution approval.

## Documentation reconciliation

The final wrap-up reconciled the current operational documentation so the historical HTTP 403 and client-action exposure stages are no longer described as current blockers:

- `docs/control/CURRENT.md` records the completed governed-action state;
- `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md` is resolved/superseded for current-state use;
- `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md` documents the accepted asynchronous Datto job workflow and current bounded action state.

## Grafana / Prometheus acceptance

Repository inspection identified the authoritative observability deployment under `infrastructure/showcase`, so the wrap-up updated the existing production-health exporter and repository-provisioned Grafana dashboards instead of inventing a separate dashboard write path.

The observability changes added:

- current MCP image/source expectations for the deployed governed-action release;
- secret-safe contract checks for the exact bounded Datto execution profile, allowlist, component, endpoint, and endpoint class;
- required read-only credential mount checks including the dedicated Datto execution identity;
- `jason_datto_governed_execution_contract`, a local configuration-readiness metric that does not call Datto and does not grant authority;
- the provisioned `Jason Governed Actions` Grafana dashboard showing the production contract and dated bounded proof context.

The first monitoring-only deployment exposed an operational deployment defect: the new systemd unit file was installed, but the already-running `jason-production-health-exporter.service` process remained attached to the older September 14 worktree because `systemctl enable --now` did not restart an already-running unit. The monitoring default also still expected the prior Autotask requester mode.

Commit `9e42b4cc1666cfb2ff0efa38d4947e79bd2939e4` corrected that by:

- changing the accepted Autotask requester mode to `impersonated`; and
- explicitly restarting the production-health exporter after installing/reloading the unit.

The subsequent rollback-protected monitoring-only deployment passed. The new exporter process was verified running from the current governed-execution worktree, and the deployment reported:

- `RUNTIME_CHANGED=NO`;
- `MCP_CHANGED=NO`;
- `OPENBAO_CHANGED=NO`;
- `PROVIDER_ACCESS=NO`;
- `PROVIDER_WRITES=NO`.

Live metric verification returned `1` for all required checks, including:

- MCP running;
- accepted MCP image;
- accepted source revision mapping;
- provider-read profile;
- Autotask requester mode;
- Datto execution profile;
- Datto execution scope;
- network/port/restart contract;
- required secret-mount contract;
- `jason_datto_governed_execution_contract`.

Prometheus returned `PROMETHEUS_DATTO_GOVERNED_EXECUTION=PASS`.

Grafana successfully served:

- `jason-production-health`;
- `jason-governed-actions`.

Final monitoring acceptance output:

- `GRAFANA_GOVERNED_ACTIONS=LIVE`;
- `SECTION_GOAL_MONITORING=PASS`.

Grafana/Prometheus remain observational only. They do not call production providers directly and cannot authorize a new provider action.

## Known non-blocking metadata debt

The live MCP container still carries an inherited `JASON_SOURCE_REVISION=5ee3507...` environment value even though the verified live image is `jason-mcp:generic-governed-8f1e864947a2`. The production-health exporter therefore accepts the source revision from the immutable image/source mapping. This stale environment metadata should be normalized during a future controlled MCP recreation, not by restarting/recreating the MCP solely for cosmetic cleanup.

## Section Goal closure

The Section Goal is complete. The bounded Datto execution path is live-proven, terminally verified, documented, and represented in live Grafana/Prometheus observability while preserving Jason governance and without any additional provider mutation during the observability deployment.

## Remaining operational follow-ups

- Reconcile structured System Registry state only through the registry's governed verification model; no registry lifecycle state was invented during this wrap-up.
- Add first-class lifecycle tooling for the dedicated `datto_rmm.execution` secret identity so future credential rotation does not require rediscovery of its paths/policies.
- Normalize the stale MCP `JASON_SOURCE_REVISION` environment value during a future controlled MCP recreation.
- Expand the Datto execution allowlist/endpoint scope only through a separate governed capability/authority decision; this completed proof is not blanket execution approval.
