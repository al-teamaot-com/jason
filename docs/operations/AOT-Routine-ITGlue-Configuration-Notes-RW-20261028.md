# AOT routine IT Glue configuration-notes write slice

**Status:** Source-only provider adapter and tests; **not wired, credentialed, activated, or deployed**.
**Date:** 2026-10-28
**Scope:** Change the notes field of exactly one IT Glue configuration.

## Purpose

IT Glue currently has governed read support and proposal-only mutation planning, but not a live governed write executor. This source-only adapter is designed for Jason's existing Central Orchestrator and J-102 prepared execution-plan path, not a direct-provider shortcut.

The official IT Glue API documentation (https://api.itglue.com/developer) confirms PATCH /configurations/:id with JSON:API data.type=configurations and attributes.notes. Notes remain updateable on externally synchronized configurations even when other fields are restricted.

## Bounded provider contract

- Capability: it_glue.configuration.update; this adapter permits notes only and is not registered as active in Jason.
- Profile: JASON_IT_GLUE_ROUTINE_RW_PROFILE=configuration-notes-v1, checked at plan preparation and execution. Absent/other values disable it.
- Credentials: a separately provisioned OpenBao logical secret it_glue.readwrite. The existing it_glue.readonly secret is never used as fallback.
- Identity: an injected trusted requester/client verifier must bind an authenticated AOT technician to an exact client and its IT Glue organization. The caller cannot supply the organization mapping.
- Preflight: GET the exact configuration, verify durable ID, type, organization, unrestricted state, current notes and revision.
- Exact plan: bind PATCH target/path, notes SHA-256 commitment, length, source-state digest and revision. Raw notes and API key remain in ephemeral provider-private state.
- Execution: reverify requester/client authorization and the exact plan, check the preimage for changes, send at most one PATCH, and independently GET/read back the result.
- Duplicate suppression: if notes already match, verify and report no change. No blind retry following a timeout or ambiguous provider response.
- Audit: safe metadata only; no credentials or raw note contents.

## Not covered

No passwords, documents, bulk edits, configuration identity changes, privileged or restricted records, arbitrary provider API paths, cross-client changes, autonomous approval or production activation.

## Integration still required

1. Register the bounded operation under the existing capability registry, JKD-001 identity/authority and J-102 execution-plan path.
2. Implement the trusted technician-to-client-to-IT Glue organization boundary, with positive and negative tests against authoritative customer mapping.
3. Provision and verify a dedicated least-privilege IT Glue write credential; keep read and write credentials separate.
4. Complete end-to-end exact-request approval and durable audit/idempotency integration. Technician-requested routine changes must not require redundant owner approval; autonomous execution requires a separate approved playbook.
5. Perform a controlled test on a deliberately unrestricted, non-sensitive test configuration, including independent pre/post verification and duplicate suppression.
6. Respect the existing deployment freeze and exact-release production controls; this source PR is not a deployment approval.

## Tests and rollback

Focused tests cover authorized change, no-op, invalid fields, unknown client, inactive user, restricted/cross-client records, missing write credential, stale preimage, plan tampering, missing readback and provider 403 handling. No live provider mutation is performed in these tests.

The adapter remains unregistered and disabled by default. If activated in the future, removing the profile through governed release control prevents further execution. Reverting a change requires another authorized update based on verified previous values.
