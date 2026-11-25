# Windows Unexpected Shutdown — JSON read-only classification candidate

## Section Goal
Preserve the existing deterministic Windows Shutdown site/event classifier
in a source-bound, approval-safe PMv4 JSON candidate without production
activation or protected Core modifications.

## Source and immutable candidate
Legacy: `unexpected_shutdown@1.1.0`,
`docs/playbooks/Jason-Windows-Unexpected-Shutdown-Site-Correlation.md`.
JSON: `candidates/unexpected_shutdown.v1.json`,
`1.1.0-migration.2`; canonical fingerprint
`c23b8ed6c8091e291704daa5ec18a2696715af6a89780f0030d8d6efd1f40e61`.
The source allowed write capabilities are limited to internal Autotask
note creation and ticket status updates, with exact independently
governed Owner approval required.

## Deterministic source reuse
`json_shutdown_classification.py` imports the actual deployed
`classify_site_scope`, `shutdown_character`, `storage_health_risk`,
`site_event_id` and `protected_role` pure functions. No new heuristic
engine or provider transport is introduced.

Inputs must be exact same-company, same-site, matching device UID and
trusted event time. Only distinct physical-device events within
+/-15 minutes count toward the three-physical-device site threshold;
VMs are excluded. Missing classification, cross-client peers,
ambiguous evidence, protected hosts, WHEA/storage errors or recurring
independent failures cannot produce a clean closure decision.

Source interpreter steps declare current ticket/endpoint reads,
alert history, approved read-only Windows evidence, then a fully gated
optional managed-note and ticket-completion plan. Those latter
instructions are **not executed** by this source adapter and require
fresh independent provider readback plus exact Owner promotion.

## Tests
`test_json_shutdown_classification.py` compares source site classifier,
event character and incident identifier, then independently checks
VM exclusion, small-site review, protected server, offline device,
recurrence >= 2, unknown event, WHEA/storage and peer-time/client/site
invalidation, with zero provider mutations. JSON interpreter branch
tests prove default human review and separate approval-required
note and ticket actions.

## Outstanding full-source and preproduction acceptance
- Authoritative cross-client/site peer inventory and per-physical-device
  event correlation (including timing, site UID and ambiguity handling).
- Exact Windows event/WHEA/physical disk/reliability/volume read-only
  telemetry, fanout and parser binding to the existing source.
- Durable 30-day incident recurrence, source fingerprint and 15-minute
  window persisted across worker and process restarts.
- Independent device-health verification for every correlated endpoint,
  approved internal-note creation, exact ticket status and readback.
- Controlled live preproduction shadow acceptance, source parity
  including failures/retries, approved release and rollback evidence.

**Read-only deterministic classification: isolated synthetic PASS.**
**Full authored legacy playbook parity: INCOMPLETE.**
**Accepted replacement and live JSON activation: NO.**
