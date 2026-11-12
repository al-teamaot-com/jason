# IT Glue governed record create/update — release preparation

Date: 2026-11-12
Branch: feature/itglue-governed-records-rw-20261112
GitHub PR: https://github.com/al-teamaot-com/jason/pull/2455
Status: SOURCE ONLY. No live credentials provisioned, no live provider writes, no production activation.

## Components and exact scope

- implementation/connectors/it_glue/governed_record_write.py: J-102 prepared execution only; flexible assets create/trait updates; document metadata creation/rename; configuration creation. No delete, credential, attachment, ACL, unrestricted mutation, or bulk capability.
- implementation/connectors/it_glue/configuration_note_update.py: pre-existing separately governed source-only notes-only configuration update, not activated by this change.
- implementation/connectors/it_glue/create_claim_store.py: durable SQLite creation claims. Claim first, one POST maximum; verify by independent GET. No automatic POST retries after ambiguous failures. Creation claim is verified in database after successful provider readback.
- implementation/runtime_service/src/jason_runtime/it_glue_record_management.py: five named canonical capabilities and one dedicated provider; only an exact explicit release-controlled profile can activate, otherwise BUILDING/PLANNED and unregistered invocation.
- implementation/runtime_service/src/jason_runtime/composition.py: guarded registration and conditional J-102 invoker wiring; no effect on default production runtime when profile absent.
- implementation/connectors/core/openbao_secrets.py: separate readwrite logical secret points only to secret/data/connectors/it-glue/production/write with api_key field.
- tools/provider_secret_provision.py: add distinct it_glue_write provider policy/role/secret to existing root-governed tool; not executed.
- tools/stage_it_glue_write_runtime_credentials.py: reuse root-only role credential staging with explicit --stage (optional, separately authorized --replace-existing); no secret printing; never invoked on real credentials during development.
- infrastructure/jason-runtime/compose.it-glue-write.yaml: optional Compose override to bind only the separate write AppRole and activate an explicitly selected profile. Not part of the default Compose path.

## Governance and authorization

All writes remain on the Central Orchestrator J-102 prepared plan and the existing JKD-001 authority boundary. A client_id and principal identity are required; a trusted active Microsoft/Jason identity binding is verified. The existing SQLiteClientBoundaryRepository must prove one exact client to one IT Glue org mapping with status VALIDATED, an actual validation timestamp, and consistent reverse lookup. Cross-client, restricted, ambiguous, or stale records are rejected.

IT Glue API keys represent service-level rights, not native per-request impersonation of each technician. Jason’s existing exact-action/role/client authority remains compulsory and provider API-key rights are the ceiling of what the actual API permits; a verified Microsoft identity alone does NOT grant execution authority.

One-off provider POST may not be retried after an ambiguous result. A governed operator reconciliation workflow using provider evidence is still required before claiming production recovery readiness. The durable claim store itself is connected to the runtime authority volume only if explicit write activation occurs.

## Vendor REST provider contracts and restrictions

Documented IT Glue API routes include organization relationships for POST flexible assets, documents and configurations, and GET organization relationship document-folder by folder ID; record PATCH requests use the provider resource endpoint. The document code only creates bounded metadata (not rich document bodies). Document folder is pre-read and verified to belong to the same organization and to be unrestricted. Flexible asset PATCH replaces all traits, so this implementation merges only safe simple scalar/list traits and fails closed for complex, credential-like, linked or restricted existing fields. Successful mock transport tests are NOT a live provider acceptance test.

IT Glue API documentation: https://api.itglue.com/developer/

## Read-access recovery — separate exact release

Live IT Glue read continues failing with OPENBAO_AUTH_FAILED. Root-managed jason-boot-recovery currently reports staged credentials ALREADY_READY without checking source freshness. Source regression 88283d358 removed the previous safe freshness check. Separate draft recovery PR https://github.com/al-teamaot-com/jason/pull/2457 restores the previously verified root-managed local-source vs staged credential comparison and narrowly scoped exact-image runtime remount. This does not rotate AppRole. If the protected AppRole itself is revoked, a further governed root AppRole identity recovery is required under issue #2228. No direct shell workaround, secret exposure, or read key reuse for writes.

## Required preproduction/provider acceptance

1. Authoritatively verify a deliberately controlled IT Glue test organization/client mapped through the existing client boundary and identity systems. Record only IDs/metadata; do not expose credentials.
2. Through root-governed provisioning, create/store a distinct write API credential and least-privilege IT Glue write AppRole. Confirm preflight and staging; no fallback to read key.
3. Execute provider-backed reads under governed requester; then one isolated approved create and update in a disposable, non-restricted test resource; verify native response shapes and independent readback, negative ACL/403, cross-client denials, idempotency, reconciliation, client matching and no collateral effects.
4. Complete security and dependency review, static tests, CI, exact immutable source revision, rollback revision/artifact and independent production health canary plan.
5. Seek a new authenticated exact-SHA production release approval under existing freeze/PMV3 rules. Do not infer release authority from engineering authorization or this document.
6. Deploy only approved isolated components and verify both IT Glue functions and unaffected autonomous ticket processing and other protected-core services. Restore freeze exactly; roll back on validation failure.

## Known unresolved limitations

- Production read AppRole authentication fails. Existing root recovery may need a privileged exact-action approval beyond code deployment.
- No live write API credential or validated test organization was independently verified.
- No provider-side create/update or production rollback can be claimed.
- Activation is tested only in source and deliberately disabled in current production.
- The optional Compose overlay must pass isolated deployment checks and exact release packaging.
- Document body editing/attachments and configuration field update other than pre-existing notes-only source adapter are separate capabilities and not yet implemented.

## Test evidence and acceptance

Focused IT Glue connector and runtime composition/source tests have passed, including read regression, core write operations, schema deny rules, separate credential paths, durable claim concurrency and restricted/cross-client records. Test data are simulated; production live write acceptance has not passed. Preserve deterministic J-102 plan fingerprints, audit proof and last known good rollback.
