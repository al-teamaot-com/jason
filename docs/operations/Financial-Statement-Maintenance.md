# Financial Statement Maintenance

## Purpose

`TODO-FIN-001` is the governed Jason maintenance workflow for AOT financial statements. This independent Compose component schedules its own 05:00 `America/New_York` run, recursively scans the configured SharePoint `Bank Checking Accounts Register` root, and normalizes verified bank, line-of-credit, and credit-card statements into `Bank Statements - Organized`.

The workflow is disabled by default. Deploying the code does not activate SharePoint mutation authority.

## Production authority boundary

Use a dedicated Microsoft client boundary with provider `microsoft_sharepoint` and profile `sharepoint-write`. The Microsoft application should use the least-privilege `Sites.Selected` application permission and receive **write** access only to the AOT Accounting Documents SharePoint site. Do not grant tenant-wide `Sites.ReadWrite.All` for this workflow.

The dedicated OpenBao AppRole must resolve only the logical credential `microsoft_graph.sharepoint_write`. Directory-read or mail credentials are not accepted as a fallback.

Required independent deployment inputs:

- Reviewed read-only `config.json` with `enabled=true`, validated AOT tenant and accounting drive IDs, `root_path=Bank Checking Accounts Register`, `timezone=America/New_York`, and `run_hour=5`.
- Read-only validated SharePoint writer boundary snapshot and dedicated SharePoint-write OpenBao role/secret host paths.
- Component-owned state directory and the exact immutable image ID in the separate Compose project.

Activation requires the normal PMV3 exact-revision production authorization plus verified provider consent/site grant. Missing credentials, boundary validation, tenant/drive identifiers, or provider permission fail closed.

## Safety and completion

The implementation has no delete operation. Exact duplicates are left intact and reported. Ambiguous/unclassified documents remain in place. Canonical filename collisions fail closed. Every move/rename is provider-read back before it is counted successful.

A run with any file error is recorded but is not marked complete; it becomes eligible for another attempt after 15 minutes. An error-free run is recorded once for the local calendar day, making subsequent scheduler ticks idempotent.

The operational objective is not complete until production evidence proves the scheduler executed at/after 05:00 Eastern, the intended SharePoint root was scanned, provider mutations/readback behaved correctly, and a subsequent no-change run is idempotent.

## November 9 integration review

The source branch was merged with current `main` before CI verification. Active PR #2373 also edits runtime composition and Compose for separately governed client notifications; PR #2380 adds a disabled-by-default outbound opt-in environment setting to Compose. Those changes occupy independent settings and execution paths from the financial-statement SharePoint-write integration. Record both in PR #2336's integration coordination field and revalidate if either PR merges before this workstream.

Source integration is not permission to activate production. A dedicated SharePoint-write `Sites.Selected` site grant and OpenBao AppRole credentials must be verified before a production release can enable this workflow.

## Audit and retry evidence

The scheduler maintains two distinct records. The `financial_statement_runs` row tracks the latest local-calendar-day attempt and retry eligibility. An independent `financial_statement_events` table appends hash-linked `run_started`, `run_finished`, `move_intent`, `move_verified`, `duplicate_skipped`, `unclassified_preserved`, `already_canonical`, and `file_error` events. Previous retry events are not overwritten by a subsequent run. Hash-chain validation detects edits to existing events or broken ordering; it does **not** independently prove that the last events were never truncated, so production audit evidence also goes to the existing canonical orchestration event sink.

The canonical sink must be available before an actual provider move. If it refuses to record `financial.statement.move_intent`, the move is not attempted. Each successful move records provider readback and `financial.statement.move_verified`. The process writes no full statement contents or Graph credentials into audit metadata. Both the local record and canonical event sink must be backed up under the existing governed retention policy; no claim of cryptographic external anchoring is made.

## Known preactivation dependencies (November 9, 2026)

The source branch is not permission to write financial files in SharePoint. Production lacks an independently authorized, dedicated `microsoft_sharepoint` / `sharepoint-write` client boundary and scoped `Sites.Selected` application grant, and dedicated `microsoft_graph.sharepoint_write` OpenBao AppRole credentials are absent. This MUST NOT fall back to the existing Microsoft Graph `directory-read` identity or delegated SharePoint connector. The PMV3 production circuit breaker remains open, and no verified 05:00 operational run exists. Enable only after release approval, least-privilege write provisioning, readback acceptance, and audit validation. The 5 AM scheduling target is local Eastern time, including DST.

## November 17: independently deployable candidate (supersedes shared-runtime packaging)

The independent candidate reuses the statement processor, Graph connector, kernel tenant boundary,
OpenBao resolver and canonical `SQLiteOrchestrationEventStore`. It does NOT change `composition.py`,
`maintenance_process.py`, shared runtime packaging, or `infrastructure/jason-runtime/compose.yaml`.
The original PR #2336 must not be deployed alongside this candidate: that would create two schedulers.

`infrastructure/financial-statements/compose.yaml` is a separate Compose project with one process,
no HTTP endpoint, no Docker socket, no dependency on restarting another service, no production runtime
state mount, and CPU/memory/PID limits. It uses OpenBao on the existing `jason-core` network.
The existing `tick()` scheduling logic owns local 05:00 Eastern timing and 15-minute failed-run retry.
Schedule settings are read from a versioned read-only JSON file, not encoded in a shell cron.
The process takes an exclusive OS lock in component-owned state; a second instance fails before
constructing a writer. Graceful termination stops between cycles. In-flight Graph operations are bounded.

### Dependency and impact review

Reviewed the existing System Registry and PMv4 source-scope guard at baseline
`c999216a3df9d2422833b90403c31530c323f467`.
Dependencies: existing OpenBao, validated Kernel SharePoint boundary, Microsoft Graph, existing canonical
audit-store library, pypdf, component-owned state, and the existing immutable runtime image as build base.
Protected ticket-processing and runbook-management source globs are excluded. The shared Microsoft
secret resolver gains one allowlisted logical credential; this change is baked ONLY into the new image.
The new image snapshots source libraries; it does not modify the filesystem of existing containers.
The production Registry does not yet describe this new component/writer. Its registration and current
provider scope verification are explicit preactivation requirements, not assumed facts.
No PMv4 source, container, root policy, release controller, freeze or production state is changed.

### Build and bounded verification

Build from the exact reviewed commit using the existing local base image
`jason-runtime:release-d1b8c196dadd-bb7d28ebd5e5`, verified image ID
`sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`.
Use Docker's `default` builder because the independent container builder cannot resolve local-only images.
Pass `JASON_SOURCE_REVISION` as the full reviewed SHA. Record the built image ID and deploy that ID,
not the mutable preparation tag. Promote the same tested image; do not rebuild after acceptance.

Provider preflight is `--preflight` on the exact new image and reviewed configuration.
It resolves and lists only the intake root; it never creates folders, moves files or records a successful
scheduled run. It can be run with `enabled=false`. The scheduled process exits when disabled.
Never mount the live runtime boundary database: provision a verified boundary-only snapshot, mounted
read-only; the component copies it to its own state before using the existing Kernel repository.
Folder creation now records canonical intent before Graph mutation, as move/rename already did.
Graph pagination is restricted to the exact HTTPS Graph drive API before resolving credentials.
Retry-After beyond the bounded inline window fails the attempt rather than retrying earlier than requested.

### Activation prerequisites and rollback

This is release preparation, not activation authority. Required before claiming ready to activate:
1. Verify exact accounting-site drive ID and intake root via current provider readback.
2. Independently verify `Sites.Selected` application consent and write grant on ONLY the accounting site,
   plus dedicated writer certificate/OpenBao AppRole provisioning using the existing provisioning tool.
3. Provision the validated `microsoft_sharepoint` / `sharepoint-write` boundary and site scope; register
   the new component and dependencies through the existing Registry workflow. No directory-read fallback.
4. Review a versioned configuration derived from `config.example.json`; replace the unverified drive marker.
5. Run actual read-only provider preflight with the dedicated writer; archive evidence.
6. Complete required CI/integration review and exact-release authorization through existing Release Manager.
7. Activate ONLY the independent Compose service, verify 05:00 execution, file readback, duplicate/ambiguous
   preservation and subsequent no-change behavior. Capture PMv4 and ticket runtime image/start/health
   before and after; they must remain unchanged by this release.

Rollback of this first installation stops/removes ONLY the independent service using its own Compose project.
Preserve its state and append-only event databases for audit; keep configuration disabled. Do not stop/restart
or roll back `jason-runtime`, PMv4 or Teams. Service rollback stops future changes; it does not reverse
already completed SharePoint filing. Any provider reversal must use verified event item IDs/original paths
and separate governed authorization; no destructive blanket undo or database deletion.

November 17 evidence limitation: Jason has no registered SharePoint writer tenant boundary and its dedicated
writer host AppRole directory is absent at both documented locations. Use ONLY Jason-owned application
credentials and the governed dedicated writer profile; the user's GPT SharePoint connection is not a runtime
dependency and does not require reconnection for this objective. Existing directory/mail/group identities
are not a fallback for missing SharePoint authority. Provider write authority, dedicated-writer preflight
and production activation remain unverified. A successful build or fixture tests cannot resolve those prerequisites.

Integration coordination: #2455 — its IT Glue write profile adds separate keys to the shared OpenBao secret map and provider provisioner. The SharePoint writer keys in this candidate are distinct; re-review those dictionaries if #2455 merges first.


## November 17 process recovery

The isolated Compose service retries a fatal process exit at most five times. An intentionally disabled configuration exits successfully without creating a writer, so it does not restart. The normal per-cycle failure handler retains its one-minute loop and governed 15-minute retry eligibility. A repeated startup failure after the bounded attempts must be diagnosed and restarted through the release process; do not silently restart protected services.
