# Backup.net Full-Access Production Activation — 2026-09-24

## Purpose

Production-select the isolated Backup.net full-access credential profile while preserving Jason's existing governed read surface, client isolation, Central Orchestrator authority, and rollback path.

## Source and build

- Protected PR: #231.
- Merged source: `b2474ddbaec5173d4e828cbdf44c174c69de6395`.
- Runtime image: `sha256:0b710618b58f972f0499be127469d6d12451eb03b1c208ab0092f184aaa3a1a1`.
- MCP image: `sha256:b47fcd4d3685412c98e6325cc4491e349816ace54cb46b9c9dd179932a7f0841`.
- Focused Backup.net/provider-secret regression: 51 tests PASS.
- Runtime-service/provider-secret regression: 249 tests PASS.
- Protected GitHub CI and GitGuardian: PASS.
- Post-merge `main` validation workflows: PASS.

## Full-access secret identity

The Owner created and verified provider `backup_net_full_access` through the canonical secret lifecycle.

- logical secret: `backup_net.fullaccess`;
- KV path: `secret/data/connectors/backup-net/production/full-access`;
- AppRole: `jason-backup-net-full-access`;
- runtime artifact directory: `/var/lib/jason/runtime-secrets/openbao/backup-net-full-access-approle/`;
- KV version written: 1;
- runtime access active: true;
- persistent runtime token: false;
- secret values printed: false.

The full-access AppRole directory is `root:1000` mode `0750`; role/secret/metadata files are `root:1000` mode `0640`.

The pre-existing read-only identity was not overwritten and remains separately available for credential/profile rollback.

## Deployment

Both runtime and MCP were deployed from the exact `b2474dd` candidates with:

- `JASON_BACKUP_NET_ENABLED=true`;
- `JASON_BACKUP_NET_ACCESS_PROFILE=full_access`;
- full-access AppRole role/secret paths under `/run/jason-secrets/openbao/backup-net-full-access/`;
- both AppRole files mounted read-only.

Both hardened preflights passed before cutover.

Runtime deployment passed hardening, health, source-revision, and transactional alias promotion checks.

MCP deployment passed hardening, health, source-revision, transactional alias promotion, and `MCP_GOVERNANCE_POSTCHECK=PASS`.

Central Orchestrator remains authoritative and `direct_provider_access=false`.

The live Jason write-capability list remained unchanged and contains no Backup.net mutation capability.

## Controlled acceptance

Controlled client: Deborah Gittens Virtuol Designs LLC.

Validated Autotask company ID: `1627`.

Validated Backup.net customer UUID: `08ded7d7-e1b5-427d-83d7-874e6c699471`.

Controlled asset: `DGV-50859` / Backup.net asset ID `48E1YGBDY`.

All four governed reads succeeded through the full-access credential profile:

1. `backup.endpoint.asset.search` — correlation `corr_mcp_37eb2726957c4b2b99c098ffd40faf4b`.
2. `backup.endpoint.asset.read` — correlation `corr_mcp_1b9ce27eaa0648a886a665dceb98b4be`.
3. `backup.endpoint.backup.search` — correlation `corr_mcp_f53b8ed5d10a4ea1b95914e4325e0962`.
4. `backup.backupiq.alert.search` — correlation `corr_mcp_60ba681324e240e08ef2e275aa2478a4`.

The asset remained customer-isolated and reported `backupEnabled=true`, provider status `offline`, and last successful backup `2026-09-24T01:40:58.998Z`.

The bounded backup-history and BackupIQ-alert queries completed successfully and returned empty collections, consistent with the earlier read-only acceptance.

## Rollback

`jason-runtime:rollback-current` and `jason-mcp:rollback-current` point to immediate previous source `8362eaa4e236d585711d51b775f4f551bab78b6f`.

Only one stopped runtime/MCP rollback container pair for `8362eaa` is retained.

Older `699bf0a` rollback containers were removed after the `8362eaa` rollback pair was verified.

## Write-capability boundary

The full-access credential uses the same documented OAuth/client-credentials flow and Public API host as the read-only credential.

Provider credential scope is not Jason authority.

As of 2026-09-24, the published Backup.net Public API OpenAPI contract advertises GET operations only. Jason therefore registers no Backup.net POST/PUT/PATCH/DELETE capability and performs no provider mutation.

Any future Backup.net mutation requires a provider-supported write operation plus explicit Jason capability authority, execution-plan binding, exact target/payload validation, approval policy, readback verification, and rollback/recovery handling.

## Same-day production hardening follow-up — SUPPORT-CONN-020

Later on 2026-09-24, a governed read against AOT-50282 exposed two connector-contract defects that were not exercised by the original company-1627 acceptance:

- Atlantic Office Machines is the legitimate Autotask self-company record with company ID `0`, but the Backup.net connector and boundary helper incorrectly required a company ID greater than zero.
- `backup.backupiq.alert.search` rejected an omitted `type` locally even though a general alert search should use provider type `alert`.

PR #252 fixed both conditions without broadening provider authority. Merged production source is `87f9ecd60676db46fff5b815857b62a42f6b8320`. The fix also permits an exact unique Backup.net customer boundary to be validated when the provider proves that customer has zero Endpoint Backup assets; if assets exist, exact asset proof remains mandatory.

A validated boundary was then created for Autotask company `0` / Atlantic Office Machines to Backup.net customer UUID `08de23b9-9685-4cdf-8932-e2318bf4412a`. The provider proved that this customer currently has an empty Endpoint Backup asset inventory.

Post-deployment governed acceptance succeeded:

- AOT-50282 asset search: `corr_mcp_09b4230fe92548deb2329335c959f6de` -> successful empty collection.
- BackupIQ alert search with omitted `type`: `corr_mcp_1eaf814b3d0f40cda6793f9918a0aa4a` -> successful empty collection.
- Backup-history search: `corr_mcp_cc46dfae0cfd4d43895aa3cf281ff434` -> successful empty collection.

The empty collections are authoritative provider results for that exact validated customer boundary. They mean Backup.net currently exposes no matching protected AOT asset/history in those queries; they are not authorization or connector failures. Central Orchestrator remained authoritative and `direct_provider_access=false` throughout. No Backup.net mutation or endpoint disruption occurred.

The detailed repair/deployment record is `docs/sessions/BackupNet-SUPPORT-CONN-020-Production-Fix-2026-09-24.md`.

## Result

PASS. Full-access credential selection remains production-active for the existing governed Backup.net read surface with no expansion of Jason mutation authority. SUPPORT-CONN-020 is production-resolved, including valid Autotask company ID `0` handling and bounded default BackupIQ alert search semantics.
