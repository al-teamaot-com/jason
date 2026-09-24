# Backup.net / UniView Production Activation — 2026-09-24

## Purpose

Production-accept the governed read-only UniView / Backup.net Public API foundation for Datto Endpoint Backup and BackupIQ diagnostics tracked by issue #216 and PR #218.

## Source and release gates

- Protected `main` merge: `8362eaa4e236d585711d51b775f4f551bab78b6f`.
- PR #218 required CI, GitGuardian, provider-secret, governed-provider-read, and path-filtered MCP capability-discovery checks: PASS.
- Post-merge `main` validation workflows: PASS.
- Exact no-cache runtime and MCP candidates were built from `8362eaa` and source labels were verified before deployment.

## Secret and client-boundary controls

The existing OpenBao KV secret was preserved at version 3. The Owner reactivated the dedicated runtime AppRole through the canonical provider-secret lifecycle; the provider Client ID/Secret was not re-entered or rewritten.

Verification proved:

- provider: `backup_net`;
- runtime access active;
- field contract valid;
- no persistent runtime token;
- no secret values printed;
- runtime secret directory: `/var/lib/jason/runtime-secrets/openbao/backup-net-read-approle/`;
- directory ownership/mode: `root:1000` / `0750`;
- role/secret files ownership/mode: `root:1000` / `0640`.

The pre-existing validated client boundary was independently read from the authority store:

- boundary ID: `bnd_e83db47cb6614197854a04d52eae1298`;
- Autotask company ID: `1627`;
- provider: `backup_net`;
- Backup.net customer UUID: `08ded7d7-e1b5-427d-83d7-874e6c699471`;
- primary domain: `virtuoldesigns.com`;
- profile: `endpoint-backup-read`;
- status: `validated`.

## Authority activation

The first live MCP read correctly failed closed with `NO_MATCHING_AUTHORITY_GRANT`. Before changing authority, the production authority database was backed up with SQLite's online backup API:

`/var/lib/jason/authority/authority.sqlite3.backup-backupnet-read-20260924T103726Z`

The backup was mode `0600` and passed `PRAGMA integrity_check`.

Exactly one grant was then added:

- grant ID: `grant-aot-backup-net-provider-read-observe`;
- subject: `organization:aot`;
- capability: `provider-read:backup_net`;
- organization: `aot`;
- client: none;
- permission: `observe`;
- approval required: false;
- status: active.

Authority grant count changed exactly from 77 to 78. The provider-read matcher constrains this grant to registered read-only capabilities advertised by `backup_net`; it does not grant Backup.net write/remediation authority.

## Production deployment

Runtime and MCP were both deployed from `8362eaa` using the hardened fail-closed wrappers and transactional image-alias promotion.

Backup.net activation was applied to both containers because MCP composes its own governed runtime application in-process. Both received:

- `JASON_BACKUP_NET_ENABLED=true`;
- canonical role/secret paths under `/run/jason-secrets/openbao/backup-net/`;
- two read-only binds from the dedicated host AppRole directory.

Runtime and MCP hardening, health, source revision, canonical image promotion, and MCP governance post-checks passed. `direct_provider_access=false` remained true.

Production images:

- runtime: `sha256:9e088c99eadc51d79e0166a9e4f42282b5a4b308fbc651ef681a6a2172aa3b61`;
- MCP: `sha256:2602eceea6eac75c73d9133e72a8d84c1f3b7621d4c5829b0e907aa85dd91650`.

Immediate rollback source retained by both `:rollback-current` aliases: `699bf0a836888ca0565369ba7a8db8f0c115caf0`.

## Controlled live acceptance

Acceptance case: Autotask `T20260922.0063`, Deborah Gittens Virtuol Designs LLC, asset `DGV-50859`.

Autotask evidence confirmed the ticket identifies DGV-50859 and the named client. The ticket's `companyID=0` was not used as the provider boundary; the independently validated company ID `1627` remained authoritative.

Datto RMM resolved exactly one endpoint:

- hostname: `DGV-50859`;
- device UID: `efc455d1-1b7d-ae9c-57c1-a65008374456`;
- site: Deborah Gittens Virtuol Designs LLC;
- current state during acceptance: offline.

All four governed Backup.net capabilities completed successfully:

1. `backup.endpoint.asset.search` — correlation `corr_mcp_68dfb9418b0d432ca9797a76618b2460`.
2. `backup.endpoint.asset.read` — correlation `corr_mcp_6ce0c8d2024d4990ab0ea755ccc2b62a`.
3. `backup.endpoint.backup.search` — correlation `corr_mcp_8f2896d80cc94621a4f609944143d534`.
4. `backup.backupiq.alert.search` — correlation `corr_mcp_f17320ba047943039913dc05b53e1594`.

The exact provider asset returned:

- Backup.net asset ID: `48E1YGBDY`;
- name: `DGV-50859`;
- customer: Deborah Gittens Virtuol Designs LLC;
- customer UUID: `08ded7d7-e1b5-427d-83d7-874e6c699471`;
- backup enabled: true;
- provider state: offline;
- OS: Windows;
- storage used: `317951712000` bytes;
- last successful backup: `2026-09-24T01:40:58.998Z`;
- last online: `2026-09-24T02:49:47.371685Z`.

The bounded `/v1/backups` and BackupIQ alert searches completed successfully and returned empty collections for the current query. This is a valid provider result and is not interpreted as proof that no backup exists; the Endpoint Backup asset itself independently proves the last successful backup timestamp above.

## Acceptance result

PASS.

Jason can now use provider-native Endpoint Backup and BackupIQ evidence through Central Orchestrator with validated client isolation and without direct provider access. No Backup.net write/remediation capability was introduced, no Endpoint Backup remediation was performed, and no client endpoint was disrupted during activation or acceptance.

The broader governed BackupIQ remediation playbook remains separately controlled and must not infer remediation authority from this read-only integration.
