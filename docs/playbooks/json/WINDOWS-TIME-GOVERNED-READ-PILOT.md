# Windows Time JSON v1 — governed-read evidence pilot
**Date:** 2026-10-28
**Scope:** Isolated development and automated tests, no PM deployment or service activation
**Parent conversion:** [Draft PR #2111](https://github.com/al-teamaot-com/jason/pull/2111)
**Follow-up architecture:** [Issue #2116](https://github.com/al-teamaot-com/jason/issues/2116)

## Section Goal
Prove that a disabled JSON v1 playbook can classify **existing governed Datto RMM read responses** for one exact Windows Time alert without acquiring credentials, dispatching a remediation, closing a ticket or alert, or creating a parallel worker. Success is independent static/schema validation and controlled comparison with the existing Windows Time shadow classification. Full live runtime parity and activation remain separate milestones.

## Existing sources reused
- `GovernedAutonomyReadPort` and Jason's identity/approval/Central Orchestrator path (injection contract, no changes to it)
- `management.alert.search`, exact `endpoint.device.read`, and exact `endpoint.alert.history.search` (all existing read-only capabilities)
- `windows_time_source_shadow.py` alert signature, time parsing and recurrence constants
- `validate_playbook_document` and `JsonPlaybookInterpreter` (existing JSON v1 validator and deterministic interpreter)
- `docs/playbooks/json/candidates/windows_time_source-0.1.0-jsonpreview.json`

## Read-only binding
1. Retrieve open DRMM alerts through the existing governed read-port; search for **one exact** alert UID. An absent item in a paginated response is *unknown*, not proof of resolution.
2. Require the matching component signature, nonempty alert UID, device UID, hostname, site UID, site name, observed time source and monitor-advertised approved-source list.
3. Read exactly that DRMM endpoint UID. Require authoritative endpoint UID, hostname and site UID to match the alert, and reject mismatch or missing site. A provider read must report `status=succeeded`, `stage=completed`, the exact requested capability, Datto RMM provider, a correlation ID, and no error.
4. Treat alerts older than **24 hours** or with invalid/future timestamps as **stale**, requiring Human Review, without fetching more evidence or dispatching any action.
5. For current online endpoints, read exact endpoint alert history and demand a complete result count before treating an absence of previous alerts as authoritative. Count distinct same-device/same-site time-source mismatch UIDs within the canonical 30-day window; at three or more episodes, Human Review.
6. Do **not** infer policy approval merely because the monitor's diagnostic text says `approved list`. The dedicated Windows Time diagnostic has not been collected in this bridge. A current ordinary mismatch remains inconclusive/Human Review, not recovered or remediated.
7. Convert only validated facts into the existing disabled JSON decision interpreter. Validate the returned instruction is terminal `human_review` with no provider capability, arguments, or approval action. The verdict contains redacted provenance metadata, no raw provider response.
8. Keep retry scheduling, ticket-work lifecycle, durable waiting and operational alerts in the **existing shared runtime**, not this bridge.

## Test boundaries
`implementation/runtime_service/tests/test_windows_time_json_shadow_evidence.py` uses a fake **governed read port** with the same envelope fields observed from the live read API; it asserts the exact capability calls and their selectors, rejects mismatched identity/site/provenance, tests stale/offline/recurring and incomplete-history cases, and compares recurrence to the existing `WindowsTimeSourceShadowMaintenance` path. Only temporary SQLite is used for that legacy comparison.

The real API was separately checked (read only) on October 28: Datto RMM returned a stale, open Windows Time mismatch alert for a Riggins workstation dated August 3, 2026, plus matching device UID/hostname/site identifiers and history access. **This is an observation of provider read availability, not evidence that the new adapter was deployed or ran on production.** Do not replay that alert as a live remediation target.

## Expected classifications
- Missing object, malformed provider response, or client/device mismatch → `review_identity_blocked`
- Old, invalid or future alert timestamp → `review_stale_alert`
- Offline exact endpoint → `review_waiting_endpoint`
- Three or more distinct 30-day incidents from complete same-site history → `review_recurring`
- Incomplete/read-failed history → `review_inconclusive`
- Current mismatch without authoritative client policy and dedicated W32Time diagnostic → `review_inconclusive`

## Explicit non-acceptance
- No production composition or runtime scheduler modified.
- No live JSON registry staging/activation or promotion performed.
- No changes to `implementation/autonomous_remediation/playbook_registry.json`.
- No new permissions, reboot, user interruption, service restart, DNS change, ticket note or alert resolution.
- No claim of complete JSON runtime worker integration, durable state, live observation freshness of diagnostic component, full legacy parity or production-ready migration.

## Remaining acceptance gate
After review, validate **provider-backed** shadow run from Jason's existing maintenance loop with strict evidence provenance; confirm the exact client/site boundary and durable recheck behavior, and independently test negative cases before any runtime activation. These are release-sensitive integration steps and must use the existing governance/release process if production behavior is changed.
