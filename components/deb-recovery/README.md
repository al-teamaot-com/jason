# DEB recovery: pre-activation engineering candidate

## Result

**Not eligible for activation.** The endpoint incident is recovered, but native
Windows acceptance and the new JSON action bindings remain unverified. No
provider credentials, authority policy, production services, shared ComStore
component, scheduler or registry activation are changed by this source.

This extends the existing `backupiq_endpoint_backup` design. The candidate is
`docs/playbooks/json/candidates/backupiq_endpoint_backup.1.4.0-rc.2.json`.
The previous staged rc.1 stays immutable; neither version has execution authority.

## Corrections from the review

- Include the verified Autotask company in **every** Backup.net asset read,
  including post-repair rechecks. Missing company scope must not be diagnosed
  as broken credentials. Company ID 0 remains valid for AOT.
- A same-client fresh successful asset timestamp plus an empty exact current
  alert result can prove provider recovery. Detailed history is optional: its
  observed transport failure must not prevent that authoritative verification.
- Keep MSI results, service/registration state, provider recovery and PSA terminal
  readback as separate evidence. No command success closes an incident.
- Treat active/running backup states as waiting, not automatically offline or
  installer failure. Old/equal-baseline/future successful timestamps cannot
  establish a post-repair recovery point.
- Poll an existing asynchronous component job, preserving its exact selectors.
  Never redispatch because output is empty or job completion is uncertain.
- Use the existing v1 interpreter and checkpoint/wait mechanism, with an acyclic
  bounded graph: five one-minute job polls and twelve fifteen-minute provider
  rechecks. The trusted original three-hour deadline still wins. Do not reset
  it on restart or progress. This is not another scheduler or authority store.

## Original PowerShell helpers

`RecoveryPrimitives.ps1` declares functions only; importing it does nothing.
It is original AOT code, not copied ComStore source.

`Resolve-DebMsiSource` defaults to report-only. Before an approved copy it checks
the exact MSI hash, valid pinned public signer, installed product/version,
safe sibling filename and reparse paths. A differing existing sibling is never
overwritten. Copy is non-overwriting and its hash is checked afterward. Expected
filename must come from installed MSI source registration, not a global guess.

`Confirm-DebPostInstall` separates installer failure and reboot-required outcomes
from service verification. It defaults to report-only, never restarts a running
service, starts a stopped service only with `-Apply`, waits boundedly, and checks
the original agent and tenant using the native status tool. The caller must
already have exact maintenance authority and evidence of no conflicting backup.
No token/encryption inputs are accepted, no MSI is launched and no backup is
started by these primitives. Existing vendor inputs must be preserved when
integrating into an RMM-only maintained copy.

The current installed ComStore version 1.4/build 17 was read in RMM. It invokes
its downloaded MSI under a different source filename and has no service-start
step before registration. Its copyright confines redistribution; the vendor
body is deliberately **not** included in this repository. No live copy was edited.

## Read-only native canary package

`NativeReadOnlyCanary.ps1` plus the exact attached helper hashes in
`canary-manifest.json` form a published, **not yet executed** RMM candidate
(`6efeedfb-fc41-4cee-a499-3641efe056f4`). The input profile
contains exact nonsecret device, signed MSI and original pairing evidence only.
All global/site variables must be excluded. Unknown profile keys are rejected.
The script checks the helper hash before importing it, pins exact MSI bytes,
and invokes both helpers without `-Apply`. It never invokes an installer,
starts/restarts services, requests backups, deletes files, changes settings or
reboots. The canary's inspection of the pinned MSI's public signer is not a
standing signer policy for future modifying components.

The component was created for one approved site only, with no selected global/site
variables, an empty per-run profile default and the reviewed helper attachment.
The stored script matches the reviewed source after CRLF normalization; the
local uploaded helper hash matches the manifest. RMM reports one 7.6 KB file.
The governed component catalog independently returned this exact UID/name and
input variable. No standing approval or endpoint job was created.

The follow-up exact UID/name variable contract remains source-only. It permits
one required profile of at most 4096 characters and does not grant execution
authority. Native execution remains blocked until an authorized release installs
that contract. Do not fill the component default or bypass the governed path.
Even a successful read-only canary will not prove modifying behavior.

`deb_canary_evidence.py` reduces independently read exact job/output receipts
to narrow observations. It rejects wrong identities, incomplete/truncated reads,
ambiguous output and modifying flags. It neither calls a provider nor connects
the production JSON action runner. The existing shared JSON migration acceptance
is tracked in issue #2637; do not create a parallel dispatcher or approval store.

## Verified engineering evidence

- 55 Python cases: scoped provider evidence, strict post-repair baseline,
  identity/customer mismatch rejection, denial versus empty evidence, deadlines,
  candidate schema and semantic graph, fail-closed gates, bounded waits,
  immutable staging, shared checkpoint/resume and caller-seed rejection.
- 100 regression cases: existing BackupIQ classification, asset selection,
  JSON validation/registry, Backup.net connector/client/catalog, identity,
  audit, governed provider reads and Datto component scope.
- 15 PowerShell cases using real temporary-file hashes/copies and mocked
  Authenticode/MSI COM/SCM/native status dependencies. Passing under pinned
  PowerShell 7.4.6 on Linux **does not** prove Windows PowerShell 5.1 execution.
- PowerShell parser checks for both production-candidate files.
- Live governed asset and alert evidence replay verified a post-repair recovery
  point. A governed read-only RMM job independently reported the agent service
  Running (enum 4), automatic start (enum 2), and exit 0. No new helper ran live.

Tests are under `implementation/runtime_service/tests/test_deb_recovery_*.py`
and `Test-RecoveryPrimitives.ps1`. No real approval, mutation or activation is
created by the tests. Production evidence is kept out of public test fixtures.

## Activation gates still failing

1. Install the exact reviewed canary input contract and run native Windows 5.1
   acceptance through existing governed execution. No native MSI COM,
   Authenticode, SCM or GUI-status-process proof is inferred from mocks.
   Source tests do not install this contract. Existing protected production
   health, freeze, exact release and rollback controls must permit its release;
   a canary component in the provider catalog does not satisfy those controls.
2. Integrate the helpers into a reviewed maintained RMM component without
   redistributing the vendor source, preserving normal install and original
   registration/encryption behavior; then test the exact modifying branch under
   a separately approved maintenance canary.
3. Bind new diagnostic, repair and backup-request profiles to exact published
   component UIDs/file hashes and trusted output reducers. A JSON fact name is
   not an implemented adapter or an approval.
4. Complete existing PMv4 JSON component-mutation execution parity. The existing
   `json_governed_mutation_bridge.py` is expressly source-only and narrowly
   limited to a ticket-handoff operation. It cannot execute these DEB branches.
   Do not generalize that bridge or bypass its controls as a shortcut.
5. Demonstrate resume/idempotency, existing approval enforcement, same-client
   provider recovery, deduplicated documentation and final PSA readback through
   the governed integrated runtime. Then review exact activation separately.

Standing Security archive deletion, retention/audit changes, restore operations,
clean installs, asset lifecycle changes and reboots are excluded. The incident's
bounded archive deletion approval is not reusable fleet policy.

## Rollback

No live behavior has been changed by this source. Leave all candidates inactive;
the existing production implementation and rc.1 draft remain intact. Revert only
this isolated engineering commit if withdrawing the source. Do not change the
recovered endpoint or undo its approved space/VSS corrections as a code rollback.
