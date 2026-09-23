# Jason Datto EDR/AV Governed Read Backend Acceptance — 2026-09-18

## Scope

This record proves the production-governed Datto EDR/AV **read backend** required by the `datto_edr_av` playbook. It does not authorize or claim Datto EDR provider mutation, isolation, quarantine mutation, or provider-native scan execution.

## Production source and services

Accepted source revision:

`b63798e048f4493d15b79565e997f43f8fd7edac`

Production services after the approved restart:

- `jason-runtime`: fixed Datto EDR/AV runtime image, healthy.
- `jason-mcp-pilot`: fixed Datto EDR/AV MCP image, running.
- MCP source revision metadata: `b63798e048f4493d15b79565e997f43f8fd7edac`.
- `direct_provider_access=false` remains authoritative.
- Central Orchestrator remains the governed execution/read coordinator.

Rollback protection was created before both service restarts.

## Credential and authority boundary

Datto EDR uses the dedicated OpenBao logical secret `datto_edr.readonly` behind the dedicated `jason-datto-edr-read` AppRole.

Exactly six AOT-wide `observe` grants were added for the existing authenticated owner principal:

- `endpoint.security.status.read`
- `endpoint.security.detection.search`
- `endpoint.security.detection.read`
- `endpoint.security.policy.read`
- `endpoint.security.scan.history.search`
- `endpoint.security.quarantine.search`

No execute or administer grants were added.

Authority backup created before the grants:

`/var/lib/jason/authority/authority.pre-edr-read-grants-20260918T142417Z.sqlite3`

## Controlled target

Endpoint:

- hostname: `AOT-50282`
- Datto RMM resource UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`
- Datto EDR Agent ID: `0cf9b495-879b-4b6c-8c60-ac229e01d136`

The accepted identity rule is:

`DRMM resource UID -> Datto EDR deviceId -> Datto EDR Agent ID`

Hostname alone is not accepted as durable EDR identity because the tenant contains a stale duplicate hostname record.

## Live governed acceptance

All six provider-neutral capabilities succeeded through the real authenticated Jason MCP path.

### 1. Endpoint security status

Capability:

`endpoint.security.status.read`

Result:

- succeeded
- exactly one EDR record matched the Datto RMM resource UID
- endpoint status: Online
- EDR agent active: true
- EDR agent authorized: true
- isolated: false
- EDR agent version: `3.17.1.6224`
- Datto AV enabled: true
- Datto AV connected: true
- AV engine ready: true
- engine version: `8.4.2.30`
- VDF version: `8.21.6.116`
- reboot required: false

The initial production status-read failure exposed a canonical-selector mismatch: Jason supplied `resource_id` while the provider-native connector expected `device_uid`. Source revision `b63798e...` corrected the connector to accept the canonical `resource_id` while preserving `device_uid` compatibility and failing closed when neither durable selector exists.

### 2. Detection search

Capability:

`endpoint.security.detection.search`

Result: succeeded.

The current evidence set includes a high-severity Datto AV detection for `EXP/CVE-2016-7228` associated with `Clario Report - Physician Productivity 2025-12-22 064050.xls`.

The same alert set also contains suppressed rule detections such as VSS enumeration/inhibit activity. Suppressed rule detections are not treated as equivalent to the active AV detection.

### 3. Detection detail

Capability:

`endpoint.security.detection.read`

Current accepted provider evidence for the AV detection includes:

- `detected=true`
- `provider_compromised=true`
- normalized compromise signal: `provider_indicated`
- `execution_status=Unknown`
- `threat_status=Quarantined`
- `provider_quarantined=true`
- `provider_remediated=true`
- `provider_success=true`
- `provider_isolated=false`
- reboot needed: false

Jason must preserve this as **provider-indicated compromise**, not silently convert it to independently corroborated malicious execution or endpoint compromise.

### 4. Policy read

Capability:

`endpoint.security.policy.read`

Result: succeeded.

Assigned policy evidence includes:

- Ransomware Policy - Roll back
- Datto AV Real Time Protection
- Datto EDR active Monitoring
- Default Response Policy

### 5. Scan history

Capability:

`endpoint.security.scan.history.search`

Result: succeeded.

The provider exposes scan type, status, timestamps, and duration/history metadata. A completed scan record proves that the scan completed; it does not independently prove that the endpoint is clean.

The playbook therefore requires composite clean verification:

`completed scan record + clear post-scan governed detection search`

### 6. Quarantine history

Capability:

`endpoint.security.quarantine.search`

Result: succeeded.

The current AV detection has a matching quarantine record with `status=Quarantined`. Historical quarantine records demonstrate recurrence of the same threat signature/file pattern over multiple dates.

## Governance conclusions

The production acceptance proves:

- Datto EDR/AV read access is governed through Jason.
- Credentials remain behind OpenBao and are not exposed to ChatGPT.
- Exact AOT authority grants are required.
- All six EDR capabilities are read-only.
- No Datto EDR mutation surface was introduced.
- Durable endpoint identity is provider-cross-correlated rather than hostname-selected.
- Product health and security evidence remain separate dimensions.
- Provider `compromised=true` is preserved as provider-indicated evidence rather than asserted as independent compromise proof.
- `ScanHistoryTracking.status=completed` is not treated as a clean scan result.

## Limitation at the time of read-backend acceptance

At the time this read-backend acceptance was recorded, governed provider-native Datto AV scan execution was not yet implemented, so the full threat-remediation branch correctly remained fail-closed.

That specific limitation was resolved later on 2026-09-18 through governed `endpoint.security.scan.start`. The live AOT-50282 Quick Scan acceptance is recorded separately in `docs/sessions/Jason-Datto-EDR-AV-Scan-Execution-Acceptance-2026-09-18.md`. This historical read-backend proof remains valid and unchanged.

The playbook remains:

- lifecycle: `pilot`
- enabled: `false`
- current review status: `scan_execute_accepted_full_threat_branch_pending`

## Acceptance disposition

**Governed Datto EDR/AV read backend: ACCEPTED**

**Full autonomous/supervised threat-branch playbook activation: PENDING complete remediation/scan/recurrence acceptance. The scan-execute capability itself was subsequently accepted on 2026-09-18.**

## Live observability closeout

Completed 2026-09-18:

- persistent playbook registry: `/var/lib/jason/playbooks/registry.json`
- persistent acceptance events: `/var/lib/jason/playbooks/events.jsonl`
- playbook exporter: active and enabled under the `al` user service manager
- exporter endpoint: `127.0.0.1:9468/metrics`
- Prometheus job: `jason-playbooks`
- Prometheus target state: `up=1`
- Grafana dashboard UID: `jason-playbook-control-center`
- Grafana title: `Jason Playbook Control Center`
- original registry state shown by metrics at read-backend closeout: lifecycle `pilot`, enabled `0`, review `read_backend_accepted_scan_execute_pending`; after scan-start acceptance the review state advanced to `scan_execute_accepted_full_threat_branch_pending`
- acceptance telemetry: one `acceptance_pass` event with verification `pass` and security disposition `detection_under_investigation`

Monitoring remains observational. It does not add provider access, execution authority, or permission to mark the full threat branch production-ready.
