# Device Reconstruction and Deployment-as-Code Component Specification

**Version:** 0.1  
**Status:** Proposed  
**Owner:** Jason Architecture Authority  
**Authority:** `docs/foundation/J-002-Constitution.md`, `docs/architecture/J-100-Reference-Architecture.md`, `docs/architecture/J-101-Capability-Registry.md`, `docs/architecture/J-102-Governed-Approval-Architecture.md`, `docs/standards/J-404-Documentation-Governance-and-Continuity.md`, `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md`  
**Scope:** Governed collection, normalization, recovery documentation, drift detection, and per-device deployment-as-code generation for managed Windows endpoints.  
**Canonical source:** No — proposed component contract pending implementation review and acceptance.  
**Supersedes:** None  
**Superseded by:** None  
**Last reviewed:** 2026-09-30  
**Review interval:** On material architecture change and before production activation  
**Evidence references:** GitHub issue #661; live Jason capability registry; current IT Glue flexible-asset catalog  
**Security / data handling:** Client-isolated operational documentation. Never persist passwords, hashes, API tokens, private keys, BitLocker recovery secrets, Wi-Fi PSKs, database credentials, service-account passwords, or other credential values in reconstruction manifests, scripts, Git, tickets, or ordinary audit evidence.

## Purpose

This component exists to make every managed device recoverable from documented, evidence-backed state rather than technician memory.

The governing recovery test is:

> If this device were completely lost today — hardware, OS, local configuration and local knowledge gone — what information would a competent technician wish had been captured beforehand to restore the device and its intended role as completely and safely as possible?

Anything that materially answers that question belongs in the recovery package, subject to secret-handling and safety boundaries.

The component is not a generic inventory collector and SHALL NOT depend on a large hand-maintained matrix of client, department, server-role or workstation "what if" cases. It discovers the device from evidence, determines what is operationally significant, produces a recovery dossier and deployment-as-code package, and keeps them current when meaningful state changes.

## Governing context

This component MUST preserve:

- Central Orchestrator authority;
- `direct_provider_access=false`;
- exact requester/service-principal grants;
- provider and client isolation;
- evidence provenance;
- secrets-broker boundaries;
- policy/approval enforcement for consequential writes;
- execution-plan binding for IT Glue mutations;
- independent post-write readback;
- auditability and rollback/recovery evidence.

Observed endpoint state is evidence. It is not automatically intended state.

## Scope

### In scope

Initial target: managed Windows workstations and Windows servers visible through Datto RMM.

The component SHALL maintain, when evidence is available:

- device identity and hardware/firmware;
- OS/build and domain/workgroup state;
- disk, partition, volume, filesystem, mount-point and storage layout;
- network interfaces and IP configuration;
- Windows roles/features;
- installed software and material application configuration;
- Windows services and service startup configuration;
- scheduled tasks;
- Hyper-V host, switch, VM and storage layout;
- DHCP role and reconstructable DHCP configuration;
- DNS/server-role context where safe;
- SMB shares and reconstructable share/NTFS permissions;
- mapped drives and their authoritative source where identifiable;
- printers and ports where operationally relevant;
- local groups and material memberships;
- certificates by metadata/reference, never private-key material;
- material non-default firewall rules;
- relevant environment/registry/hosts-file configuration;
- backup/recovery dependencies;
- a generated idempotent PowerShell rebuild script;
- a manual/unresolved recovery-dependency list;
- evidence and material-state fingerprints.

### Out of scope

The documentation workflow itself SHALL NOT:

- execute a generated rebuild script on a production endpoint;
- promote currently observed drift into intended state without policy;
- export/store credential values;
- reconstruct a domain/forest/PKI/database unsafely as though it were a stateless role;
- replace authoritative backup/recovery processes for stateful workloads;
- write client-specific reconstruction artifacts to the public Project Jason repository.

Script execution is a separate governed action with exact-target validation and applicable approval/autonomy controls.

## Authoritative statements

### 1. Per-device recovery package

Each managed device SHALL have one logical recovery package bound to durable client and device identity.

The package contains:

1. **Device Reconstruction Profile** — technician-readable IT Glue record.
2. **Normalized Reconstruction Manifest** — machine-readable state used for comparison and generation.
3. **Deployment Script** — generated idempotent PowerShell sufficient to recreate safely reconstructable state.
4. **Recovery Dependencies** — external/manual steps and data sources.
5. **Evidence Map** — source, observation timestamp, and provenance for material facts.
6. **State Fingerprint** — normalized hash used to suppress unnecessary updates.

The IT Glue Configuration remains the primary durable device identity. Detailed rebuild state SHOULD live in related structured documentation/flexible assets rather than configuration notes.

### 2. Identity binding

Before collecting or publishing:

1. resolve the Datto RMM device by durable device UID;
2. resolve client/site;
3. correlate Autotask configuration where present;
4. resolve exactly one IT Glue organization;
5. resolve the IT Glue device/configuration relationship;
6. verify durable identity using the strongest available combination of provider UID, serial/service tag, configuration identity, and client mapping.

Hostname alone is not sufficient when stronger identity exists.

Ambiguous identity MUST fail closed.

### 3. Evidence model

Evidence SHOULD come from existing governed capabilities before new custom collection is added.

Initial sources include:

- `endpoint.device.read/search`;
- `endpoint.audit.read`;
- `endpoint.software.search`;
- `endpoint.powershell.read`;
- Autotask service configuration reads;
- IT Glue organization/configuration/flexible-asset/document reads;
- backup-provider reads where applicable.

PowerShell collection MUST be read-only and bounded. It SHOULD fill evidence gaps, not duplicate provider audit without reason.

### 4. Worst-case adaptive discovery

The collector SHALL use a **discover -> interpret -> expand -> classify -> document** model.

It starts from a universal baseline and automatically increases collection depth according to what it finds on the endpoint and in authoritative provider/documentation evidence.

Examples:

- DHCP role detected -> collect scopes, reservations, exclusions, options, bindings, policies and authorization state.
- Hyper-V detected -> collect switches, VM definitions, storage/config/checkpoint paths, disk attachments, VLANs and replication.
- SMB shares detected -> collect share settings, backing paths, share permissions and recovery-relevant NTFS ACLs.
- IIS detected -> collect sites, bindings, app pools, content/config paths and certificate references.
- Print services/shared printers detected -> collect queues, ports, drivers and share configuration.
- Non-default scheduled tasks detected -> collect triggers, actions, arguments, run-as identity and recovery significance.
- LOB application/service detected -> identify install source, prerequisites, service dependencies, config/data paths and recovery dependencies where evidence permits.
- Domain Controller detected -> switch to AD-aware recovery documentation rather than treating it as a generic role reinstall.
- Persistent mapped drives detected -> identify whether the authoritative source is local configuration, GPO, logon script or another managed source.
- Unusual services, listeners, folders, registry settings or startup items detected -> investigate whether they are operationally significant before deciding whether to include them.

Role/device understanding SHOULD use multiple corroborating signals where practical, including:

- Windows roles/features;
- services and startup configuration;
- installed software;
- network/listener evidence;
- scheduled tasks;
- storage paths;
- registry/configuration evidence;
- shares/printers;
- provider metadata;
- existing IT Glue documentation;
- backup/recovery evidence.

Jason MAY use reusable role interpreters and evidence collectors, but these are generic capability modules rather than a client-by-client decision tree.

A new or unusual device SHOULD be recoverable without first writing a new playbook. If Jason discovers something it does not yet know how to reproduce safely, it MUST still capture the evidence, explain why it may matter, and classify it as a recovery dependency or manual-review item rather than silently omit it.

### 5. Worst-case inclusion rule

For every discovered fact, Jason asks:

> Would losing this information make worst-case recovery slower, riskier, less accurate, or dependent on rediscovery?

If **yes**, the fact or a safe reference to it belongs in the recovery package.

If **no**, it may be omitted from the recovery package even if it is useful general inventory.

This rule takes precedence over maintaining exhaustive static field lists.

Jason SHALL classify recovered knowledge into:

- `AUTO_REBUILD` — safely reproducible from generated code;
- `RECOVERY_SOURCE` — must be restored/imported from an authoritative backup, secret, certificate, configuration, installer or other recovery source;
- `MANUAL_REVIEW` — important to recovery, but evidence is insufficient or automation would be unsafe;
- `REFERENCE_ONLY` — useful context that may help a technician but is not required to recreate intended function;
- `VOLATILE` — runtime noise that should not drive rebuild documentation or IT Glue updates.

Unknown-but-potentially-important discoveries default toward documentation/review, not omission.

### 6. Reconstruction coverage

#### Hardware and firmware
Capture manufacturer, model, serial/service tag, BIOS/UEFI details, Secure Boot/TPM state, CPU, RAM, and physical storage/controller evidence where obtainable.

#### Storage
Capture physical disks, partition style, partitions, volumes, filesystems, drive letters, mount points, labels, sizes, storage spaces/pools, and BitLocker state. BitLocker recovery material is referenced only by governed recovery source/presence.

#### Networking
Capture adapter identity/model/MAC, enabled state, static versus DHCP, IPv4/IPv6, prefix/subnet, gateway, DNS servers, suffix/search list, VLAN/team/binding state where observable, non-default routes, and relevant Windows network profile/firewall context.

#### Windows roles and features
Capture installed Windows roles/features and use them as role-module triggers during script generation.

Examples:
- DHCP Server;
- DNS Server;
- Hyper-V;
- File Services;
- Print Services;
- IIS;
- AD DS.

Stateful roles MUST use role-specific safety policy rather than generic reinstallation behavior.

#### Services
Capture material services, display/name, binary path where safe/useful, startup mode, dependencies when material, and service-account identity without secret values.

#### DHCP
When DHCP is present, the recovery package SHOULD include enough evidence and generated logic to:

- install the DHCP role;
- recreate scopes;
- recreate reservations;
- recreate exclusions;
- recreate scope/server options;
- restore bindings and policies where safely supported;
- validate authorization state;
- identify any externally required secrets/data.

Generated DHCP configuration MUST be idempotent.

#### DNS and Active Directory
Capture role presence and safe reconstructable metadata.

A domain controller MUST NOT be treated as a generic standalone server rebuild. The package SHALL point to the applicable authoritative AD/System State recovery path and backups. Automatic domain/forest recreation is out of scope unless a separately approved recovery playbook governs it.

#### Hyper-V
Capture:

- host role/features;
- virtual switches and physical bindings;
- VM names, IDs and generation;
- vCPU;
- startup/static/dynamic memory;
- automatic start/stop behavior;
- VM configuration paths;
- VHD/VHDX locations and controller attachment;
- checkpoint and smart-paging locations;
- VLAN configuration;
- replication configuration/status where applicable;
- passthrough/physical-disk references where present.

Generated code MAY recreate host features, virtual switches, folder layout and VM definitions where safe. Guest data recovery MUST reference authoritative storage/backup sources.

#### File shares
Capture all material non-default SMB shares:

- share name;
- local path;
- description/settings;
- share permissions;
- reconstructable NTFS ACL information;
- DFS/namespace relationship when applicable.

Generated code SHOULD recreate required folders, ACLs and share definitions idempotently where safely representable.

#### Mapped drives
Capture persistent drive mappings and their source.

The collector SHOULD distinguish:

- machine/local persistent mappings;
- per-user mappings;
- GPO-delivered mappings;
- logon-script mappings;
- temporary/transient mappings.

Transient user state MUST NOT become intended machine state without corroborating evidence.

Where GPO or logon script is authoritative, the recovery profile SHOULD record/reference that source rather than generate competing local configuration.

#### Applications
Capture installed software, versions, relevant install/config/data paths, services, prerequisites, and install source when discoverable.

Generation priority:

1. AOT-approved Datto component;
2. vendor-supported unattended installer/package;
3. native Windows capability/package source;
4. documented manual step.

Jason MUST NOT fabricate an installer or silently assume licensing/credentials.

#### Scheduled tasks
Capture material non-default tasks including trigger, action, arguments, working directory, run-as identity, and settings. Recreate only when no undisclosed secret is required.

#### Printers
Capture operationally relevant printers, drivers, TCP/IP ports or UNC paths, share names, and applicable configuration. Recreate only when a valid driver/package source is known.

#### Local identities
Capture material local groups/memberships and only those local accounts required for service/application operation. Never store passwords/hashes.

#### Certificates
Capture certificate subject, issuer, thumbprint, store, EKU/intended purpose, expiration and private-key-presence flag. Record recovery/import source by reference. Never place private keys or PFX passwords in ordinary documentation.

#### Firewall
Capture material non-default Windows Firewall rules: direction, action, profile, protocol/port, program/service and remote/local scope. Recreate only intended rules.

#### Environment and machine configuration
Capture material time-zone, domain/workgroup membership, hosts-file custom entries, operationally relevant non-secret environment variables, non-default PowerShell policy where material, and selected registry state required by known applications/roles.

#### Backup and recovery dependency
Capture the authoritative backup asset/source, recovery method, and what must be restored rather than recreated.

The package SHALL explicitly flag recovery-critical data lacking a known authoritative recovery source.

### 7. Deployment-as-code generation

Windows v1 generates PowerShell.

Generated code MUST be:

- idempotent;
- phase-oriented;
- manifest-bound;
- client/device-bound;
- deterministic from accepted evidence;
- free of credential values;
- safe to review without executing;
- explicit about manual dependencies;
- able to validate postconditions;
- versioned and fingerprinted.

Recommended phases:

1. preflight / target validation;
2. operating-system prerequisites;
3. disk/folder layout;
4. network baseline;
5. Windows roles/features;
6. role-specific configuration;
7. applications and managed agents;
8. services and scheduled tasks;
9. shares, mapped-drive dependencies and printers;
10. security/firewall configuration;
11. recovery-source integration/manual dependencies;
12. validation report.

Generation MUST consume the recovery classification produced by adaptive discovery. In particular:

- `AUTO_REBUILD` items become generated idempotent configuration logic;
- `RECOVERY_SOURCE` items become explicit restore/import/reference steps;
- `MANUAL_REVIEW` items become technician actions or blockers;
- `REFERENCE_ONLY` items remain context;
- `VOLATILE` items do not drive generated rebuild logic.

### 8. Intended-state model

The component SHALL maintain two distinct views:

- **Observed state:** latest authoritative evidence from the live endpoint/providers.
- **Accepted reconstruction state:** state Jason is allowed to publish as the current recovery definition.

An observed change does not become accepted reconstruction state solely because it exists.

Examples requiring review or corroboration:

- a critical Windows role disappears;
- a Hyper-V VM path moves unexpectedly;
- a production share vanishes;
- a static server address changes unexpectedly;
- a scheduled task or service appears/disappears;
- an application materially changes without known change evidence.

Expected, low-risk inventory changes MAY be auto-accepted under a promoted policy.

### 9. Drift and refresh behavior

The component runs on a governed schedule and on demand.

A normal cycle:

1. resolve identity and scope;
2. collect current evidence;
3. normalize into stable state;
4. strip volatile/non-recovery noise;
5. calculate material-state fingerprint;
6. compare with last accepted/observed fingerprints;
7. classify drift;
8. regenerate only affected reconstruction sections;
9. propose or perform governed IT Glue update according to authority;
10. independently read back the written target;
11. record evidence and next state.

No material change means no IT Glue content rewrite.

Recommended initial observation cadence:

- servers: daily;
- workstations: weekly;
- immediate/on-demand after a major approved configuration change or before decommission/replacement.

The cadence is configuration, not embedded authority.

### 10. IT Glue representation

Existing AOT flexible-asset types already include:

- ITGLue AutoDoc - Server Overview;
- ITGLue AutoDoc - Physical Host v2;
- Workstation Application Baseline;
- Workstation Specifications;
- ITGLue AutoDoc - Device logbook;
- Virtualization.

Implementation SHALL evaluate those schemas before creating another flexible-asset type.

If none can cleanly own the full recovery contract, create one deliberate type such as **Device Reconstruction Profile** and relate it to the IT Glue Configuration. Do not create multiple overlapping auto-doc types.

A profile SHOULD provide concise technician sections plus references/attachments for generated manifest/script when IT Glue field size or structure makes embedding inappropriate.

### 11. IT Glue writes

The repository currently contains an IT Glue mutation proposal implementation for:

- `it_glue.document.create`;
- `it_glue.document.update`;
- `it_glue.flexible_asset.create`;
- `it_glue.flexible_asset.update`;
- `it_glue.configuration.update`.

Those writes are not active in the live Jason capability registry as of this proposal.

Write enablement SHALL be implemented through the existing governed JIS mutation architecture rather than through a new direct API path.

Before production write activation, require:

- exact capability registration;
- least-privilege IT Glue write identity;
- client scope validation;
- side-effect-free write plan;
- execution-plan/argument binding;
- idempotency;
- before-state capture;
- post-write readback;
- audit correlation;
- deterministic client-isolation tests;
- owner review for any autonomous update branch.

### 12. Artifact placement

Client-specific reconstruction data MUST remain in client-isolated approved storage, preferably IT Glue/approved operational artifact storage.

The public Project Jason repository MAY contain:

- schemas;
- generators;
- role modules;
- generic templates;
- tests;
- documentation.

It MUST NOT contain:

- client manifests;
- real IP plans tied to clients;
- client share/ACL inventories;
- per-device deployment scripts;
- client-specific application/license details;
- secrets or secret-bearing exports.

## Boundaries and dependencies

### Existing useful capabilities

- `endpoint.device.read/search`
- `endpoint.audit.read`
- `endpoint.software.search`
- `endpoint.powershell.read`
- `service.configuration.read/search`
- `documentation.organization.read/search`
- `documentation.configuration.read/search`
- `documentation.flexible.asset.read/search`
- `documentation.flexible.asset.type.read/search`
- `documentation.document.read/search`
- backup-provider reads

### Required new/extended capabilities

Expected gaps include:

- normalized device reconstruction collector capability;
- accepted/observed reconstruction state persistence;
- script/manifest artifact storage;
- IT Glue flexible-asset/document write activation;
- per-write readback verification;
- scheduler/drift runner;
- role-specific reconstruction modules;
- optional relationship/link management between IT Glue configuration and recovery asset.

No new direct-provider path is authorized by this specification.

## Verification / evidence

A controlled acceptance test SHALL use a non-critical approved endpoint or XYZ Test Company target.

Acceptance proves:

1. exact client/device identity;
2. full read-only collection;
3. shares and ACL capture;
4. mapped-drive source classification;
5. disk/partition layout capture;
6. role/service/task capture;
7. Hyper-V/DHCP module behavior when present;
8. normalized manifest generation;
9. deployment-script generation;
10. secret scan passes;
11. generated script is syntactically valid;
12. dry-run/plan output is target-bound;
13. no generated script is executed during documentation testing;
14. unchanged second scan produces no IT Glue rewrite;
15. controlled material change produces a bounded diff;
16. ambiguous/cross-client mapping is rejected;
17. governed IT Glue write/readback is proven once write capability is active.

## Failure / drift handling

Fail closed when:

- client identity is ambiguous;
- endpoint identity is ambiguous;
- required provider evidence is unavailable and omission would make the recovery package materially misleading;
- script generation would require an unknown secret;
- a stateful role cannot be safely represented;
- observed drift conflicts with previously accepted intended state;
- IT Glue target cannot be uniquely identified;
- write-plan target/payload changes after authorization;
- post-write readback does not match intended update.

Partial recovery coverage is permitted only when gaps are explicit.

## Change / rollback / retirement

Documentation and scripts are versioned/fingerprinted.

When a published reconstruction state is later determined incorrect:

- preserve prior evidence/version history;
- restore the last accepted representation where appropriate;
- record why the state was rejected;
- regenerate from corrected evidence;
- verify IT Glue readback.

The component can be disabled without deleting client recovery records.

## Initial implementation sequence

### Phase 1 — collector and manifest
Build the bounded read-only Windows reconstruction collector and normalized schema. No IT Glue writes.

### Phase 2 — generator
Build generic PowerShell generator plus modules for common Windows baseline, storage/folders, roles/features, services/tasks, networking/firewall and SMB shares.

Add role modules incrementally for DHCP and Hyper-V first.

### Phase 3 — IT Glue publisher
Activate governed IT Glue create/update capabilities using the existing JIS mutation architecture. Implement exact target mapping and readback.

### Phase 4 — drift/cadence
Add scheduled collection, stable fingerprinting, no-op suppression and bounded drift classification.

### Phase 5 — autonomous documentation updates
After acceptance testing, nominate only narrowly safe documentation-update branches for owner promotion. Unexpected/high-impact drift remains review-bound.

## Related records

- GitHub issue #661 — Device Reconstruction & Deployment-as-Code documentation
- `docs/control/JASON-FUNDAMENTALS.md`
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
- `docs/engineering/jis/JIS-Provider-Development-Guide.md`
- `docs/architecture/J-101-Capability-Registry.md`
- `docs/architecture/J-102-Governed-Approval-Architecture.md`
- `implementation/connectors/it_glue/`
- `docs/components/capabilities/Dormant-Read-Only-Endpoint-PowerShell.md`

## Revision notes

- 0.2 — Made worst-case recoverability the governing inclusion test and replaced static what-if logic with adaptive evidence-driven discovery.
- 0.1 — Initial proposed recovery-documentation and deployment-as-code component specification.
