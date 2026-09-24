# Backup.net SUPPORT-CONN-020 Production Fix — 2026-09-24

## Purpose

Document the diagnosis, source fix, protected merge, production deployment, client-boundary correction, rollback posture, and live governed acceptance for SUPPORT-CONN-020.

The incident affected Datto Endpoint Backup / BackupIQ governed reads for AOT. It did not require or authorize any Backup.net mutation.

## Initial failure

A live AOT-50282 check reproduced two independent failures at the `backup_net` connector boundary:

- `backup.endpoint.asset.search` failed with `CONNECTOR_AUTHORIZATION_DENIED`.
- A general `backup.backupiq.alert.search` failed with `CONNECTOR_CONFIGURATION_ERROR`.

A retry of BackupIQ with explicit `type=alert` passed argument validation but then failed with the same authorization denial as the asset search.

Datto RMM remained healthy for AOT-50282, so the failure was isolated to the Backup.net governed-read path rather than a general Jason or provider outage.

## Root cause

Two source defects were confirmed.

### Valid Autotask company ID 0 was rejected

Atlantic Office Machines is the legitimate Autotask self-company record and uses company ID `0`.

The Backup.net connector and boundary-provisioning helper converted `company_id` to an integer and rejected values below `1`. That incorrectly treated AOT company `0` as invalid and failed before provider execution.

The corrected rule accepts non-negative exact Autotask company IDs and continues to reject booleans, non-integers, and negative IDs.

### BackupIQ general search incorrectly required type

The connector required `type` for every `backup.backupiq.alert.search` call even though a general alert search should use the provider's alert class.

The corrected rule:

- defaults omitted `type` to `alert`;
- preserves the explicit allowlist for supplied values: `alert`, `job`, `conditional`, or `helix`;
- continues to reject unsupported explicit values before provider execution.

## Zero-asset customer boundary handling

Read-only provider discovery established exactly one Backup.net customer named `Atlantic Office Machines`:

- Backup.net customer UUID: `08de23b9-9685-4cdf-8932-e2318bf4412a`.

A bounded provider inventory query returned zero Endpoint Backup assets for that exact customer. Therefore AOT-50282 could not be used as asset proof.

The boundary helper was hardened to support this legitimate condition without weakening client isolation:

- if provider assets exist, exact asset proof remains mandatory;
- if the exact unique provider customer is established and a bounded asset query proves the customer's inventory is empty, the customer may be validated as a zero-asset boundary;
- a caller still may not supply the Backup.net customer UUID as authority.

This permits governed reads to return the provider's authoritative empty result instead of failing authorization before provider access.

## Source fix and tests

Fix branch:

`fix/support-conn-020-backupnet-aot-zero`

Source commit:

`b3f81291041aff59866c87e27ee7397fb6722f48`

Protected PR:

`#252 — Fix SUPPORT-CONN-020 Backup.net reads for AOT`

Merged production source:

`87f9ecd60676db46fff5b815857b62a42f6b8320`

Focused regression coverage included:

- valid company ID `0`;
- negative company-ID rejection;
- BackupIQ default alert type;
- explicit BackupIQ type allowlisting;
- zero-asset customer proof;
- rejection of zero-asset mode when provider assets are present;
- existing Backup.net connector and runtime-composition behavior.

Focused result:

`33 tests passed`.

No production provider mutation was part of testing.

## Production build and deployment

Exact candidates were built from merged source `87f9ecd60676db46fff5b815857b62a42f6b8320`.

Runtime image:

`sha256:207f0aa1f03b8d3f97360bcd27d0273a516247579bc34838293ac46fbf171cb1`

MCP image:

`sha256:f4cf7ae385a3457ff3dfce7865b3615187ac7615cd037badf4dd867c5df431e1`

Both candidates passed source-revision provenance checks and hardened deployment preflight.

Production deployment preserved the existing Backup.net full-access and DNSFilter environment/bind configuration explicitly.

Runtime deployment passed:

- preflight;
- hardening verification;
- health verification;
- source-revision verification;
- image-alias promotion.

MCP deployment passed:

- preflight;
- hardening verification;
- health endpoint verification;
- source-revision verification;
- image-alias promotion;
- `MCP_GOVERNANCE_POSTCHECK=PASS`.

Post-deployment governance remained:

- Central Orchestrator authoritative;
- generic governed execution enabled;
- `direct_provider_access=false`;
- no Backup.net mutation capability registered.

## Rollback posture

Immediate rollback aliases were preserved.

Runtime rollback:

- source: `fe75d15304a294fe20193c5c837f9f99be74e4ee`;
- image: `sha256:94b3c5bb3c07863f5b1836c62be91d020423be1eafd2347002f433478047c362`.

MCP rollback:

- source: `5244e9e41ac86a366fc475b37be0559919fdc968`;
- image: `sha256:785279fe3ea25145dea7e55bd4256656999adc4bd7fc2f838cbf66877f7ba901`.

Before the AOT client-boundary write, the boundary database was backed up to:

`/var/lib/jason/authority/client-boundaries.sqlite3.backup-support-conn-020-20260924T1543Z`

The backup was restricted to mode `0600`.

## AOT client-boundary activation

The validated boundary created after provider proof is:

- boundary ID: `bnd_821e905fdc344225b0cabdfa49ff5081`;
- Autotask company ID: `0`;
- company: Atlantic Office Machines;
- provider: `backup_net`;
- external customer UUID: `08de23b9-9685-4cdf-8932-e2318bf4412a`;
- primary domain: `teamaot.com`;
- profile: `endpoint-backup-read`;
- status: `validated`;
- provider asset proof: empty inventory.

No provider credential value was printed or persisted into documentation.

## Live governed acceptance

### AOT-50282 asset search

Capability:

`backup.endpoint.asset.search`

Correlation:

`corr_mcp_09b4230fe92548deb2329335c959f6de`

Result:

- status: succeeded;
- provider: `backup_net`;
- returned collection: empty.

Interpretation: Backup.net currently exposes no matching Endpoint Backup asset for AOT-50282 under the exact validated Atlantic Office Machines customer boundary.

### BackupIQ general alert search

Capability:

`backup.backupiq.alert.search`

The caller omitted `type`, exercising the regression fix.

Correlation:

`corr_mcp_1eaf814b3d0f40cda6793f9918a0aa4a`

Result:

- status: succeeded;
- provider: `backup_net`;
- returned collection: empty.

This proves omitted-type general alert search no longer fails local configuration validation.

### Backup history search

Capability:

`backup.endpoint.backup.search`

Correlation:

`corr_mcp_cc46dfae0cfd4d43895aa3cf281ff434`

Result:

- status: succeeded;
- provider: `backup_net`;
- returned collection: empty.

## Operational interpretation

An empty collection after successful governed execution is not a connector failure.

For the AOT customer boundary, current provider evidence means no matching protected Endpoint Backup asset/history is exposed under that customer/query. If AOT-50282 or another AOT endpoint is expected to be protected, the next investigation should focus on provider onboarding, registration, customer placement, stale/renamed assets, or other provider-side inventory conditions.

Do not reclassify the empty result as authorization failure and do not bypass the validated client boundary.

## Security and authority result

PASS.

The repair restored expected governed read behavior without expanding authority.

- no Backup.net provider mutation occurred;
- no endpoint was disrupted;
- no client boundary was inferred from hostname alone;
- no caller-supplied customer UUID was accepted;
- no provider secret value was exposed;
- Central Orchestrator remained authoritative;
- `direct_provider_access=false` remained enforced.

SUPPORT-CONN-020 is production-resolved.
