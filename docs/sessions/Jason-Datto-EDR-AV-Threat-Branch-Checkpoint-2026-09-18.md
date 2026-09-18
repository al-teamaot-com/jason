# Jason Datto EDR/AV Threat-Branch Checkpoint — 2026-09-18

## Section Goal
Complete the Datto EDR/AV threat branch through governed remediation/scan/post-scan verification/recurrence handling without allowing healthy product state to imply threat resolution.

## Source change
Commit `9d84764` binds the playbook to the live governed `endpoint.security.scan.start` action and exact endpoint-security status, detection-search, and scan-history reads. It also corrects the stale source-only `endpoint.security.scan.execute` name.

A follow-up deterministic recurrence helper requires exact SHA-256 equality, a distinct alert, and a later timestamp when timestamps are available. It never correlates recurrence from hostname, filename, or threat label alone.

Focused playbook/connector validation: 67 tests passed.

## Controlled live checkpoint
Target: AOT-50282 / Autotask T20260918.0005.

Exact endpoint UID `69571572-83f7-1e33-9cdf-01717d4e74a4` mapped to exact EDR agent `0cf9b495-879b-4b6c-8c60-ac229e01d136`.

Protection state was healthy: endpoint online, AV enabled/connected, engine ready, current VDF evidence, and no reboot required.

Originating Datto AV detection `c3aa92e3-92af-4c8f-889a-51bafa50790f` was quarantined/remediated. Provider evidence also reported `compromised=true`; Jason preserves this only as provider-indicated compromise evidence and does not independently relabel it confirmed compromise.

Recurrence evidence is material: the exact SHA-256 `4ee005ac00377b12ba7aac38d9582646dc3d4dcc4feb0818bd3ecf0a8b7db2f7` appears in separate high-severity quarantined detections on 2026-09-11 (`99c2fe1b-3500-4dad-8e62-ad79359636f2`) and 2026-09-18 (`c3aa92e3-92af-4c8f-889a-51bafa50790f`). Therefore the threat branch correctly fails closure despite healthy protection state.

A Full Datto AV scan was already in progress with provider timestamp `2026-09-18T22:30:51.452Z`. Jason did not dispatch a duplicate scan.

Autotask internal note `30503131` records the checkpoint. Governed note correlation: `corr_mcp_action_e3e404478908449bb1d2cfa8f23b4fec`; provider attempts 1; readback verified.

## Safety result
No endpoint remediation, reboot, isolation, or other disruptive action was performed. `direct_provider_access=false` remains invariant.

## Closure state
**PARTIAL / FAIL-CLOSED ACCEPTANCE PASSED.** The critical safety behavior is proven: healthy EDR/AV state cannot close a recurring/provider-indicated threat. Full production activation remains pending the terminal result/readback of the already-running Full scan plus final deployment/telemetry reconciliation. The playbook remains pilot/disabled until those gates are satisfied.

## Continuation poll
At the continuation poll, governed endpoint status still reported the Full Datto AV scan `in-progress` with provider scan timestamp `2026-09-18T22:30:51.452Z`. Governed scan history had not yet emitted a corresponding new terminal Full-scan record. Jason therefore preserved the scan-pending state and did not redispatch.

Registry review status is now `threat_recurrence_gate_proven_scan_terminal_pending`; lifecycle remains `pilot` and `enabled=false`.
