# Windows Time JSON v1 — Production-release candidate (read-only shadow)

> **Review-only candidate; not approved for release.** This original 2026-10-28 source narrative is reused by the 2026-10-29 Stage C restack against narrowed Stage B1. Prior stage sequencing and merge instructions are historical; independent exact-head CI, provider proof and owner exact-SHA authorization remain required.

**Date:** 2026-10-28
**Release scope:** Governed, read-only classification comparison only; **not autonomous repair**.
**Source dependency:** Draft conversion PR #2111 → governed-evidence PR #2118 → this release-candidate branch.
**Runtime governance:** Central Orchestrator / JKD-001; `direct_provider_access=false`; exact requester and provider/client boundaries; no provider writes.

## 1. Section Goal
Prove the existing scheduled Windows Time shadow worker can safely host one *additional, optional* JSON v1 classifier, using the same previously governed Datto RMM read-port, without restarting another worker or modifying endpoints, tickets, alerts, approval stores, or existing work state. **Success is a tested build with a disabled-by-default switch, source-pinned JSON candidate, isolated persistent evidence state, safe canary scope, fail-closed diagnostic decisions, and independently recorded results.**

## 2. Trigger and strict scope
- Existing `windows_time_source_shadow_enabled` worker reads open DRMM alerts on its existing 15-minute cadence.
- The JSON classifier only considers a bounded, fairly rotated subset of exact time-source mismatch alerts on **explicitly allowed Datto site UUIDs**.
- No site is in scope by default. An empty allowlist while the JSON switch is on is a startup validation failure.
- A monitor's claim that a time source belongs to an approved list is **not** authoritative site policy. The JSON path cannot autonomously classify a repair or close a ticket.

## 3. Implemented runtime contract
- `implementation/runtime_service/src/jason_runtime/windows_time_source_shadow.py`: existing worker and persistence; adds optional JSON observer only, with feature flag and no changes to legacy decision logic. Each JSON observer failure is caught and counted without interrupting existing legacy classification.
- `windows_time_json_shadow_evidence.py`: verifies exact alert, device and site identifiers, status/stage/provider/correlation evidence; rejects stale (>24-hour) or future-timestamp alerts; verifies complete same-site device history and deduplicated 30-day recurrence. Uses only `management.alert.search`, `endpoint.device.read`, `endpoint.alert.history.search`, through the already-governed read-port. No arbitrary command, client-supplied facts or new provider API.
- `SQLiteWindowsTimeJsonShadowState`: separate SQLite DB, mode 0600, stable fingerprint and one durable verdict per exact alert; records first/last seen, classification, provenance IDs and only bounded metadata. Never stores raw provider messages or secrets.
- `windows_time_source_shadow_composition.py`: validates the *exact* `windows_time_source@0.1.0-jsonpreview` document and disables all executable capability steps before injecting it into the existing worker. Invalid JSON fails startup only when opt-in is enabled.
- `composition.py`, Dockerfile, Compose and .dockerignore: image includes **only** the reviewed JSON candidate, owned by the image runtime group and read-only to runtime UID 1000. Optional observer defaults **off**, with separate DB and strict site UUID allowlist.
- Configured maximum JSON alert assessments per tick: 25 (allowed range 1–100). A deterministic round-robin window prevents permanent starvation among matches returned on the current provider page. Deferred and outside-scope counts are observable. No new scheduler is introduced.

## 4. Current acceptance evidence and limitations
- Existing draft PR #2111: 16 original JSON v1 candidates validated; the newer `client_information_request@1.0.0` source registry entry remains separately governed and unconverted by canonical Python validator, with source reconstruction and synthetic decision tests.
- Existing draft PR #2118: governed response envelope tests, same-client identity, stale/recurrence/negative evidence and no-write tests passed.
- **This candidate** adds integration tests for existing-worker coexistence, no extra alert-list read, separate persisted state across restart, meaningful-change-only audits, JSON errors not breaking legacy processing, bounded round-robin selection, exact-site canary restriction, malformed/version-mismatched JSON fail closed, and Docker packaging/disabled-default contract. CI result and exact review SHA must be attached before release approval.
- Existing Datto RMM provider data confirmed read capability availability; an old Riggins alert dated 2026-08-03 was found in an authorized **read-only** check. This is **not** an on-host test of the new adapter or proof of alert resolution.
- The JSON pilot never claims the dedicated Windows Time component diagnostic or independent site-approved NTP policy is verified. Therefore all JSON decisions remain terminal Human Review. **Do not promote this to an automated repair playbook.**
- The DRMM account alert search may paginate. Missing from a partial page means **unknown**, never resolved. The current 25-per-tick rotation covers only the alerts returned in the queried page; wider provider pagination is a future coverage improvement.

## 5. Release gating — owner and PM-controlled, not performed here
1. Review and merge the three stacked draft PRs in order through AOT's existing controlled change/release process, with exact commits and rollback point. No automatic merge/deploy.
2. Prove CI security/validation and the container image build for the **exact release SHA**, including the JSON candidate present and readable at `/app/config/json-playbooks/windows_time_source-0.1.0-jsonpreview.json`.
3. First deploy with `JASON_WINDOWS_TIME_JSON_SHADOW_ENABLED=false` and independently verify the original Windows Time shadow worker's existing health/15-minute cadence. All other JSON variables are inert.
4. Only with a specific approved canary site, set `JASON_WINDOWS_TIME_JSON_SHADOW_SITE_UID_ALLOWLIST` to a real, exact Datto site UUID and enable `JASON_WINDOWS_TIME_JSON_SHADOW_ENABLED=true`. Keep `JASON_WINDOWS_TIME_SOURCE_SHADOW_ENABLED=true`.
5. Verify within at least two normal 15-minute maintenance cycles: no new worker, no provider write capability invoked, exact site isolation, correct stale/offline/recurring Human Review classifications, stable verdict fingerprint with unchanged evidence, bounded scans, and no increase in legacy worker failures. Inspect only sanitized audit and read-only SQLite verdicts.
6. Record exact canary evidence, source SHA, rollback instructions, failed/partial coverage, and independent authorization before expanding the site allowlist. No implicit all-client promotion.

## 6. Switches and rollback

| Variable | Default | Production canary requirement |
| --- | --- | --- |
| `JASON_WINDOWS_TIME_SOURCE_SHADOW_ENABLED` | existing true in Compose | Must remain true |
| `JASON_WINDOWS_TIME_JSON_SHADOW_ENABLED` | **false** | Explicit PM-reviewed opt-in |
| `JASON_WINDOWS_TIME_JSON_SHADOW_SITE_UID_ALLOWLIST` | empty | One or more exact, canonical Datto site UUIDs |
| `JASON_WINDOWS_TIME_JSON_SHADOW_MAX_ALERTS_PER_TICK` | 25 | Bounded 1–100 |
| `JASON_WINDOWS_TIME_JSON_SHADOW_DOCUMENT_PATH` | image-owned exact v0.1.0 JSON | Do not point at unreviewed source |
| `JASON_WINDOWS_TIME_JSON_SHADOW_DB` | isolated SQLite in /var/lib/jason/openclaw | Persisted, locally owned 0600 |

**Immediate rollback:** under the existing governed deployment/release process set `JASON_WINDOWS_TIME_JSON_SHADOW_ENABLED=false` and restart only via approved deployment authority. The original worker and its existing SQLite DB are unchanged; keep JSON state for audit. If broader runtime checks fail, revert to last-known-good exact source/image through the existing PM process. **This document does not authorize a restart or change to a live host.**

## 7. Completion decision
The code can become **release-candidate ready** when the exact revision passes CI and image packaging validation. **Production accepted** requires an independently approved, observed canary and post-release verification. **Autonomous Windows Time remediation remains out of scope** until a dedicated read-only Windows Time diagnostic, authoritative client/site time policy, exact scoped repair capability and approval binding, retry/recheck parity and independent healthy-state verification all pass their own acceptance tests.

No production activation, secret access, disruptive action, ticket update, or new authority is performed by this branch.
