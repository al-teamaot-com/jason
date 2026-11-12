# IT Glue governed records RW — source-only implementation (2026-11-12)

## Status and boundary

**Source-only; not registered, credentialed, enabled, or deployed.** This change must not be represented as working production write access. Existing production ticket processing, IT Glue read connector, authorization services, and root-managed production configuration are untouched.

Existing source:
- `implementation/connectors/it_glue/configuration_note_update.py` — separately authored, dormant, configuration-notes-only PATCH adapter;
- `implementation/connectors/it_glue/mutations.py` — proposal-only mutation planner;
- `implementation/connectors/it_glue/governed_record_write.py` — new source-only create and bounded metadata/trait update adapter.

The new adapter uses Jason's existing J-102 `ProviderPreparedExecution` contract, exact client boundary verifier, independent credential resolver, canonical plan binding, and readback. Its `execute()` method always fails closed; only a future explicitly registered Central Orchestrator invocation may run prepare/execute.

## Bounded provider operations

- `it_glue.flexible_asset.create`: one flexible asset associated with a verified mapped organization, known type, approved nonsensitive trait keys, and durable caller intent key.
- `it_glue.flexible_asset.update`: merge an approved bounded traits patch into one unrestricted client asset, with preimage/revision check.
- `it_glue.document.create`: create a metadata-only document in one verified same-organization folder. Does not upload attachments or author rich document bodies.
- `it_glue.document.update`: rename one unrestricted document (no body, restriction, publication, or attachment mutation).
- `it_glue.configuration.create`: create a named configuration with one supplied configuration type within the verified organization.
- Existing `it_glue.configuration.update`: source-only, notes-only from the 2026-10-28 adapter; not registered.

No deletes, password/secret/vault changes, permissions/ACL changes, arbitrary JSON:API payloads, raw URLs, bulk mutations, or autodiscovery of target clients.

## Mandatory preproduction wiring

1. Verify exact IT Glue documented create routes, JSON:API types/attributes, document-folder endpoint, provider-native permissions and response details with a controlled test account. The test transport is not provider acceptance.
2. Inject existing authenticated requester authorization and authoritative AOT client-to-IT Glue organization mapping. Deny ambiguous and cross-client targets and restricted records.
3. Provision `it_glue.readwrite` as a separately governed credential; never fall back to `it_glue.readonly`. Diagnose/restore the existing `it_glue.readonly` OpenBao AppRole authentication separately.
4. Supply an existing atomic, durable, restart-safe claim ledger for creation, and a provider-backed reconciliation path for ambiguous outcomes. This implementation claims once before POST and refuses any automatic second attempt; successful create readback alone is insufficient for restart/crash recovery.
5. Register explicit canonical capabilities and provider mappings using the existing registry/JKD-001/J-102 authorization chain. Do not activate all writes by enabling a catchall mutation connector.
6. Use a reviewed enablement profile `JASON_IT_GLUE_RECORDS_RW_PROFILE=governed-records-v1`, exact approved release, immutable artifact, rollback SHA, positive and negative native provider tests, audit evidence, and independent production health checks.
7. Test restricted documents, cross-client boundaries, ambiguous creates, provider 403/429/5xx, stale updates, no-op verification, and cross-provider regression. Preserve existing protected-core services.

## Explicit limitations

- This source-only adapter does not implement full IT Glue CRUD. It intentionally does not write document content, attachments, or arbitrary configuration fields.
- Generic Flexible Asset fields are treated as untrusted. Credential-like field names are blocked. An existing asset with such field names is not eligible for the merge-path update.
- Creation requests must supply a unique stable intent key and use a durable once-only claim. A missing claim ledger prevents POST.
- The current live IT Glue read path returned `OPENBAO_AUTH_FAILED` on a governed organization search on 2026-11-12. A root-managed existing recovery timer is enabled and reports success, but repeated `RUNTIME_CREDENTIAL_STAGING=ALREADY_READY` messages do not demonstrate valid IT Glue AppRole login. No credential values or private keys were inspected.
- No provider mutation or production deployment took place in preparation of this source change.

## Test evidence

Run `PYTHONPATH=implementation:implementation/runtime_service/src python3 -m pytest -q implementation/connectors/tests/test_it_glue_governed_record_write.py implementation/connectors/tests/test_it_glue_configuration_note_update.py`. Tests include exact-plan tampering, one-shot creation, immutable scoped reads, merge prevention for sensitive traits, denial for cross-client folders, no-op update, stale preimage, restricted record, and failed readback. This is mocked transport verification, not live acceptance.
