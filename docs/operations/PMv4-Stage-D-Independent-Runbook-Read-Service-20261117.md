# PMv4 Stage D — independent runbook read/hot-load component

**Status: source-only; not installed, production-authorized, or operational.**

Reuse the one existing `SQLitePlaybookRegistry` and its authenticated MCP
stage/activate/retire operations. This component independently serves only
fresh read-only snapshots from that same database, over a local UID-checked
Unix socket. No second registry, provider client, scheduler, Owner identity,
approval system, token/key, API endpoint, network egress, or parallel writer.

The source closure is `autonomous_remediation/{__init__,playbook_document,
playbook_store,runbook_management_read_service}.py` in one versioned
`/usr/local/lib/jason/runbook-management/current` package. The proposed
systemd unit supervises only this new component and must not restart
`jason-runtime` or `jason-mcp-pilot`. Source tests verify hot readback after
the **existing governed** registry changes, audit consistency, no provider
execution, no write socket route, fail-closed paths, and isolated lifecycle.

**Deployment still requires:** protected-main CI, immutable source and rollback
packet, exact Owner-approved root/systemd installation and path projection,
live existing-registry readback, service and socket health, configuration
change and retirement readback through the already governed MCP, two real
ticket-core scans, unchanged freeze and protected containers, and rollback.
Do not interpret this read-only service as a complete independent write plane
or production acceptance until those gates are observed.
