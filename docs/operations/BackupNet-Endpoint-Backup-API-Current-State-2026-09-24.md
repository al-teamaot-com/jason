# Datto Endpoint Backup / Backup.net API Current State — 2026-09-24

## Purpose

This document is the current operational record for Jason's Datto Endpoint Backup / UniView / Backup.net integration. It separates provider-supported API contracts from product UI capabilities, historical API families, and unsupported/private implementation details.

Historical activation records remain evidence of what was deployed and accepted at the time. This document governs the current interpretation of which Endpoint Backup operations Jason may implement.

## Current authoritative conclusion

Jason has a production-accepted, client-bounded **read** integration for Datto Endpoint Backup v2 / UniView through the published Backup.net Public API.

The Endpoint Backup v2 product itself supports operational actions including on-demand backup start, pause/resume protection, policy assignment and configuration, retention management, asset deletion, file-level recovery, alternate-agent restore, ZIP/download recovery, Bare Metal Recovery, Recovery Operations tracking, and cancellation of eligible recovery operations.

As of the 2026-09-24 documentation review, **no provider-supported public API contract has been identified that documents those Endpoint Backup v2 operational actions for third-party API integration**.

Therefore:

- product UI capability must not be treated as API capability;
- the full_access Backup.net credential profile does not create Jason write authority;
- Jason must not use private browser/UI endpoints to implement operational writes;
- no Endpoint Backup provider mutation capability is authorized or registered;
- current remediation remains through separately governed endpoint/RMM actions where those actions are already supported and authorized;
- provider-native Endpoint Backup state must be used for post-remediation verification and ticket closure.

## Production Jason state

Current production integration:

- provider: backup_net;
- enabled: JASON_BACKUP_NET_ENABLED=true;
- access profile: JASON_BACKUP_NET_ACCESS_PROFILE=full_access;
- logical secret: backup_net.fullaccess;
- Central Orchestrator remains authoritative;
- direct_provider_access=false;
- provider credential scope is not Jason authority.

Current governed capabilities:

- backup.endpoint.asset.search;
- backup.endpoint.asset.read;
- backup.endpoint.backup.search;
- backup.backupiq.alert.search.

Current authority remains read-only:

- grant: grant-aot-backup-net-provider-read-observe;
- capability: provider-read:backup_net;
- permission: observe.

No Backup.net/Endpoint Backup provider write grant exists.

Controlled acceptance remains:

- Autotask company ID: 1627;
- client: Deborah Gittens Virtuol Designs LLC;
- endpoint: DGV-50859;
- Backup.net asset ID: 48E1YGBDY;
- Backup.net customer UUID: 08ded7d7-e1b5-427d-83d7-874e6c699471;
- backupEnabled=true;
- accepted last successful backup observation: 2026-09-24T01:40:58.998Z.

See:

- [Backup.net production activation](../sessions/BackupNet-Production-Activation-2026-09-24.md)
- [Backup.net full-access production activation](../sessions/BackupNet-Full-Access-Production-Activation-2026-09-24.md)

## API and product families

### 1. UniView / Backup.net Public API

**Base URL**

- https://public-api.backup.net
- OpenAPI/Swagger: https://apidoc-public-api.backup.net/swagger/public_api-v1/swagger.json

**Authentication**

Jason's validated integration uses the documented OAuth/client-credentials model.

**Status**

Current, provider-published public API.

**Applicability**

This is the current Jason API for UniView-managed Endpoint Backup v2 assets such as DGV-50859.

**Documented read surface observed**

The published Swagger includes GET operations for resources including:

- assets;
- Endpoint Backup asset aliases under /api/epb/v1/assets;
- backups;
- BackupIQ alerts;
- customers;
- agent-version/download metadata;
- other UniView product/resource reads.

**Documented write/manage surface**

No POST/PUT/PATCH/DELETE operations were advertised by the published Public API contract during the 2026-09-24 review.

**Jason decision**

Continue using this API for production Endpoint Backup evidence. Do not infer write operations from the existence of a full-access credential or from actions visible in the UniView UI.

### 2. Datto REST API / Partner Portal API

**Base URL**

- https://api.datto.com

**Authentication**

Official Datto documentation describes public/secret API keys with HTTP Basic authentication.

**Status**

Current, supported Datto REST integration surface.

**Officially documented purpose**

Datto describes this API as a scalable integration mechanism for retrieving device, agent, and backup status information. Datto's current VSA 10 Endpoint Backup integration also instructs administrators to configure a Datto data portal at https://api.datto.com using a public and secret API key.

**Endpoint Backup applicability**

This API remains relevant to the Datto Partner Portal / older Endpoint Backup integration family. Datto currently documents Endpoint Backup v1 and v2 as separate portal experiences:

- Endpoint Backup v1 backups remain in Datto Partner Portal;
- Endpoint Backup v2 is managed in UniView.

Current VSA 10 documentation explicitly marks the old "Endpoint Backup for PC" deployment path unsupported and directs customers toward the Endpoint Backup v2 deployment process.

**Write/manage and restore API status**

The official Datto REST documentation reviewed on 2026-09-24 describes the integration in status-retrieval terms. No supported Endpoint Backup restore, backup-now, policy, retention, agent-management, recovery-cancellation, or decommission API contract was located in the official materials reviewed.

This is **not** evidence that no such private implementation exists. It means Jason does not currently have a documented provider-supported contract that may be used for those writes.

**Jason decision**

Do not switch Endpoint Backup v2 operational writes to https://api.datto.com based on product role names or API-key "full access" terminology alone. Treat this surface as a supported read/integration candidate for Partner Portal/legacy Endpoint Backup data until Kaseya provides an explicit supported write contract.

### 3. Endpoint Backup v2 / UniView product operations

The current product documentation confirms that Endpoint Backup v2 itself supports the following operations in UniView.

**Backup/protection management**

- Start an on-demand backup without waiting for the next scheduled run.
- Pause scheduled backups.
- Resume/start a paused asset.
- Assign a backup policy.
- Configure schedules, inclusions/exclusions, retention, and alerting through policy management.
- Delete an asset from UniView.

**Recovery**

- Browse/select recovery points.
- File-level recovery.
- Restore to the original agent.
- Restore to an alternate agent.
- Restore to a new location.
- Download selected files as a ZIP bundle.
- Single-file multi-version recovery.
- Bare Metal Recovery.
- Track restore status in Recovery Operations.
- Cancel eligible in-progress or paused recovery operations. Cancellation removes partial data already written to the destination and cannot be undone.

These are **documented product capabilities**, not proof of a public API mutation contract.

### 4. Historical Backup.net API families

Historical references such as:

- direct.backup.net;
- Tenant API;
- Customer/Organization API;
- Storage API;

must be treated as historical or unverified until a current Kaseya/Datto document explicitly identifies the endpoint, authentication contract, support status, and product applicability.

The 2026-09-24 review did not establish any of these as the supported operational-write API for current UniView Endpoint Backup v2 assets.

**Jason decision**

Do not implement against these names or endpoints from archived examples, old integrations, or browser traffic alone.

### 5. Unitrends REST API

Unitrends has separate REST/API concepts for backup jobs, appliances, recovery, and restores. UniView can display multiple backup products, including Unitrends, but that does not make the Unitrends appliance API the Endpoint Backup v2 API.

No provider documentation reviewed establishes the Unitrends appliance REST API as a supported management path for the same epb_windows / Backup.net Endpoint Backup v2 assets represented by DGV-50859.

**Jason decision**

Treat Unitrends appliance operations as a different provider/product family unless Kaseya publishes an explicit cross-product API contract.

## Current BackupIQ / Endpoint Backup process for Jason

### 1. Resolve the client and exact asset

1. Start from the actual Autotask ticket.
2. Resolve the exact Autotask company/client.
3. Require the validated Autotask-company-to-Backup.net-customer boundary.
4. Resolve the exact Backup.net asset within that customer boundary.
5. Correlate the DRMM endpoint as independent supporting identity/evidence when available.
6. Fail closed on missing, duplicate, ambiguous, or cross-client matches.

Hostname alone is not sufficient to cross a client boundary.

### 2. Establish provider-native backup state before remediation

Use the governed Backup.net reads before deciding that remediation is required:

1. backup.endpoint.asset.read
   - protection/backup-enabled state;
   - provider asset state;
   - last successful backup;
   - storage/asset metadata where available.
2. backup.endpoint.backup.search
   - bounded backup/recovery-point history where the provider returns it.
3. backup.backupiq.alert.search
   - current provider alert evidence.

Do not substitute DRMM online state, Windows service state, or successful component execution for proof of a successful backup.

### 3. Use endpoint diagnostics as supporting evidence

When the endpoint is online and the BackupIQ playbook's availability gate is satisfied, use governed DRMM/component diagnostics to inspect:

- Endpoint Backup agent installation;
- service/process state;
- version;
- relevant local Endpoint Backup logs;
- installation/remediation prerequisites such as required site-variable presence.

These checks explain *why* the backup is unhealthy. They are not the final backup-health authority.

### 4. Current remediation path

Until a supported provider-write API is documented, Jason may use only separately governed remediation paths that already have provider support and explicit authority, such as an approved Datto RMM deployment/reinstall component.

Jason must not translate UniView UI actions into private HTTP requests.

If resolution requires a provider-native action that Jason cannot perform through a supported governed API, escalate that action to a technician and document the blocker.

### 5. Post-remediation verification and ticket closure

A successful endpoint component job is not sufficient for closure.

After remediation:

1. verify the agent/service state locally;
2. re-read the exact Backup.net asset through the validated client boundary;
3. confirm a new authoritative successful backup timestamp/state;
4. re-read relevant BackupIQ alert state where applicable;
5. document the exact provider evidence in the original Autotask ticket;
6. complete the ticket only when the playbook's closure criteria are satisfied.

## Provider-write capability boundary

Do not register the following or equivalent capabilities until a provider-supported mutation contract is documented and reviewed:

- backup.endpoint.backup.start;
- backup.endpoint.restore.start;
- backup.endpoint.restore.cancel;
- backup.endpoint.protection.update;
- backup.endpoint.policy.update;
- asset delete/decommission operations.

When a supported provider operation becomes available, each mutation must have:

- a provider-neutral capability definition;
- canonical arguments;
- exact client/customer/device resolution;
- selected provider and endpoint binding;
- normalized provider payload;
- intent and execution-plan fingerprint binding;
- explicit approval policy;
- disruptive-action gating where applicable;
- exactly one provider invocation;
- post-write authoritative readback;
- unknown-outcome recovery behavior;
- bounded retry rules;
- audit and correlation IDs;
- Autotask ticket documentation;
- rollback/recovery semantics;
- a controlled production acceptance target.

Restore-to-original-agent, overwrite-capable restores, BMR, deletion/decommission, and other potentially user- or data-disruptive operations require explicit technician approval even if a future API technically permits them.

## Official documentation reviewed

- Backup.net Public API Swagger: https://apidoc-public-api.backup.net/swagger-ui-v2/index.html
- Datto REST API integration setup: https://continuity.datto.com/help/Content/kb/siris-alto-nas/360016394931.html
- VSA 10 Datto Endpoint Backup integration: https://help.vsa10.kaseya.com/help/Content/1-Modules/integrations/datto-endpoint-backup.htm
- Endpoint Backup v2 dashboard/actions: https://continuity.datto.com/help/Content/kb/EB2/EB2-dashboard.htm
- Endpoint Backup v2 policy configuration: https://continuity.datto.com/help/Content/kb/EB2/EB2-create-backup-policy.htm
- Endpoint Backup v2 recovery: https://continuity.datto.com/help/Content/kb/EB2/EB2-restores.htm
- Endpoint Backup v2 Recovery Operations/cancellation: https://continuity.datto.com/help/Content/kb/EB2/EB2-recovery-operations.htm
- Endpoint Backup v1-to-v2 portal distinction: https://continuity.datto.com/help/Content/kb/EB2/EB2-upgrade-v1-v2.htm

## Review trigger

Re-run this API-family review when Kaseya/Datto:

- adds non-GET operations to the Backup.net Public API;
- publishes an Endpoint Backup v2 operational API;
- documents supported restore/backup/policy/device mutation operations on https://api.datto.com;
- publishes an explicitly supported replacement for historical Backup.net API families.
