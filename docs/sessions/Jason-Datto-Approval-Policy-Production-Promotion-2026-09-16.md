# Jason Datto Approval Policy — Production Promotion Proof — 2026-09-16

## Section goal

Promote the server-controlled Datto component approval policy to production while preserving Jason governance, provider isolation, exact grants, rollback capability, and production observability.

## Production boundary

- MCP container: `jason-mcp-pilot`
- source: `26704f0600bbc6c48c790c9b9ff501a3b5ec3aad`
- image: `jason-mcp:generic-governed-26704f0600bb`
- rollback container: `jason-mcp-pilot-rollback-20260916T172806Z`
- Central Orchestrator: authoritative
- `direct_provider_access=false`
- write authority: `jason_exact_grant_plus_server_governed_approval_policy`
- Datto policy: `server_classified_standing_safe_or_per_run`

## Active Datto production scope

Exactly two components are classified `standing_safe`:

1. `Get-DNS Settings AOT Ver 06042025-1`
   - UID: `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`
2. `Check Datto EDR/AV Status AOT Ver 12122025-1`
   - UID: `8cb0f063-5875-452e-88ad-2e1748ed0fd0`

Target remains `AOT-50282`, device UID `69571572-83f7-1e33-9cdf-01717d4e74a4`, class `Desktop`, under `AOT governed diagnostic pilot`.

No reboot component is included.

## Approval behavior

- `standing_safe`: no separate per-run technician approval is required after server classification.
- `per_run`: explicit technician approval is required for the exact execution.
- caller-supplied approval classification is not authoritative.
- unknown/missing/invalid classification fails closed.
- user-disruptive operations remain explicit-approval-only.

## Validation

Focused Datto policy tests passed.

Candidate offline contract validation confirmed both production components resolve as `standing_safe`, neither requires explicit approval, and the MCP governed execution surface includes the explicit approval input used for `per_run` execution.

Production promotion completed successfully with no Datto provider mutation and no component execution during deployment.

Post-promotion MCP status reported:

- `mode=governed-read-plus-actions`
- `governed_execution=central-orchestrator`
- `generic_execution_tool=true`
- `direct_provider_access=false`
- `write_authority=jason_exact_grant_plus_server_governed_approval_policy`
- `datto_component_approval_policy=server_classified_standing_safe_or_per_run`

## Observability reconciliation

Monitoring source: `cefa32e9b14db97fb8c6e703ad467a9eda33c32b`

Monitoring deployment completed with:

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

Grafana dashboard UID: `jason-production-health`

Monitoring rollback directory: `/tmp/jason-production-health-rollback-20260916T173323Z`

## Acceptance conclusion

The server-controlled Datto approval policy is live. Trusted non-disruptive diagnostics may execute under `standing_safe` without an additional approval prompt, while disruptive/state-changing components remain `per_run` and require explicit technician approval. Central Orchestrator, exact grants, provider isolation, bounded scope, and fail-closed behavior remain preserved.
