# CCC Recurring Constitutional and Compliance Certification

**Status:** Implemented in source; production activation pending  
**Owner:** Jason Governance Authority  
**Related:** TODO-GOV-005; `CCC-Last-Known-Compliant-Recovery.md`; J-900 Release and Recovery Pipeline

## Purpose

CCC provides a deterministic recurring certification loop for Jason's current production state. It does not grant execution authority and it does not replace the J-002 Constitution, owner review, Central Orchestrator, JKD-001, provider/client boundaries, or J-900 recovery controls.

The default effective cadence is **30 days**. The systemd timer wakes once per day only to determine whether certification is due or whether a material source change requires an out-of-cycle run. `cadence_days` is configured in `/var/lib/jason/ccc/ccc.json`; changing the effective cadence does not require source or unit-file edits.

## Deterministic result states

A full run ends in exactly one of:

- `PASS` — every required deterministic check passed and any required material-change owner review is bound to the exact source revision;
- `FAIL` — authoritative evidence shows a required control is unhealthy or contradictory;
- `NOT_PROVEN` — required evidence/authority is unavailable, the checker is stale for a governance-sensitive source change, source/runtime alignment is not certifiable, or material owner review is missing;
- `NOT_DUE` — daily scheduler check found neither cadence expiry nor a material change;
- `DISABLED` — governed configuration disables scheduled execution.

Only `PASS` may call the Last Known Compliant promoter. `FAIL` and `NOT_PROVEN` never move the compliant pointer.

## Scheduled execution

Canonical units:

- `infrastructure/ccc/systemd/jason-ccc.service`
- `infrastructure/ccc/systemd/jason-ccc.timer`

The timer checks daily at approximately 06:15 America/New_York with a bounded randomized delay. The runner performs the expensive certification only when due.

Canonical configuration:

- source default: `config/ccc/default.json`
- production file: `/var/lib/jason/ccc/ccc.json`

The installer preserves an existing production configuration rather than replacing it during an upgrade.

## CCC service authority

Live provider boundary canaries use a dedicated non-human JKD-001 identity:

`jason-ccc-worker`

It receives exactly eight `observe` grants, with no client wildcard mutation authority and no approval bypass:

1. `service.ticket.search`
2. `endpoint.device.read`
3. `endpoint.security.status.read`
4. `dns.protection.organization.read`
5. `backup.endpoint.asset.search`
6. `print.device.search`
7. `identity.user.search`
8. `system.registry.search`

Provisioning is explicit and audited by `tools/provision_ccc_authority.py`. The scheduled provider canaries execute through JKD-001 and Central Orchestrator by reusing Jason's governed autonomous observe request path. They do not import MCP and bypass its authentication boundary, and they do not call provider APIs directly. Datto RMM/EDR, DNSFilter, Backup.net, and System Registry are positive read canaries. Autotask, Microsoft Graph, and Kyocera KFS are deliberate negative controls for requester/provider eligibility boundaries under this non-human identity; CCC requires those denials to remain exact rather than weakening them to obtain a green result.

## Certification checks

When a full CCC run is due, the runner verifies at minimum:

- authoritative `origin/main` revision;
- checker/source currentness for configured governance-sensitive paths;
- source/live-runtime alignment for configured runtime-sensitive paths;
- exact owner review when material-change prefixes have changed since the Last Known Compliant source;
- all nineteen J-002 certification matrix articles remain `PROVEN` and the final 100% certification decision remains present;
- System Registry deterministic validation;
- J-900 release validation including Kernel/CAP-001 tests, documentation-control validation, strict documentation build, and whitespace checks;
- production-equivalent MCP constitutional certification suite, with Docker/Buildx state isolated under `/var/lib/jason/ccc/docker`;
- zero failed systemd units other than the currently executing `jason-ccc.service` itself; CCC cannot use its own transient prior failure as evidence against the host;
- all configured Prometheus targets healthy;
- current OpenClaw/JKD-001 operational health snapshot is `pass` and fresh;
- `/opt/jason/current` resolves to the exact live MCP runtime revision;
- MCP governance reports `central-orchestrator` and `direct_provider_access=false`;
- all configured governed provider boundary canaries match their expected outcomes through the dedicated CCC observe identity. Positive canaries must succeed; requester-bound negative controls must continue to fail closed with the expected denial reason.

## Material changes and owner review

Configured material paths cause an out-of-cycle CCC run even when the monthly cadence has not expired. If a material change is present, CCC requires `/var/lib/jason/ccc/material-review.json` to approve the **exact current source SHA**. A prior review cannot authorize a later revision.

The owner-review record is created explicitly with:

```bash
python3 tools/record_ccc_material_review.py \
  --source-revision <40-character-sha> \
  --recorded-by person-al \
  --reason "<review rationale>"
```

This preserves the constitutional distinction between deterministic verification and requirements that still need human architectural or governance judgment.

## Runtime-changing release transition (SUPPORT-OPS-057)

The Release Manager must invoke an independent **fresh** CCC full run at the exact
candidate SHA before starting production mutation. No CCC result is assumed from
a previous release, and no owner approval overrides an actual CCC denial.
For an unchanged runtime, every CCC check and the overall result must be `PASS`.
For a reviewed and immutable runtime-changing candidate, the **only** admissible
pre-mutation exception is `runtime-source-alignment=NOT_PROVEN` with the overall
result `NOT_PROVEN`, the current live revision matching the recorded rollback
baseline, and **all other checks explicitly `PASS`**. This is a bounded
*transition preflight*, not a certification or Last Known Compliant checkpoint.
Any missing check, stale report, source/revision mismatch, checker staleness,
failed canary, owner-review gap, unexpected `NOT_PROVEN`, or `FAIL` blocks
promotion before provider, runtime or host mutation.

After runtime, MCP, and host are reconciled and functionally verified, the
Release Manager runs independent CCC again against the exact live candidate.
Every check and the overall result must be `PASS` **before** recording
`production_verified`, `closed`, or updating the release manager's Last Known
Good. A post-mutation CCC failure follows the existing governed rollback path
and persists the failed release evidence; it must not be reported as a
successful production release. Both CCC run IDs, exact revisions, and per-check
statuses are included in the durable release record and final evidence bundle.

This does not authorize production writes. The exact release owner approval,
material owner review, preproduction artifact digests, locked transaction,
protected drift/circuit-breaker controls, and verified rollback remain mandatory.
A source change to this gate creates a **new SHA and new release identity**;
prior approval for an earlier candidate does not transfer.

## Checker staleness

A scheduled checker must not certify a materially changed certification mechanism using old rules. If current authoritative source changes a configured checker-sensitive path after the installed CCC release, the runner returns `NOT_PROVEN` until the CCC control release is updated.

## Evidence and recovery

Full-run reports are stored under:

`/home/al/Jason-Evidence/CCC/runs/`

The latest full result is mirrored to:

`/var/lib/jason/ccc/latest.json`

A PASS invokes `tools/promote_ccc_checkpoint.py` / `LastKnownCompliantPromoter`, producing the restore-verified recovery package and atomically advancing:

`/home/al/Jason-Evidence/CCC/last-known-compliant.json`

## Production installation

The CCC control plane has its own immutable release path so installing or upgrading the checker does not change the live MCP/runtime source revision:

- releases: `/opt/jason/ccc-releases/<sha>`
- current checker link: `/opt/jason/ccc-current`

Install an exact reviewed source revision with:

```bash
sudo tools/install_ccc_scheduler.sh <source-revision> [material-review-json]
```

Any change to the installed immutable CCC checker revision requires a private, explicitly approved `person-al` material-review record bound to the exact new source SHA. The installer retrieves its approval preflight helper from the exact immutable Git source revision being installed, never from the operator's potentially old or dirty working-tree files. The installer validates that record **before making any production filesystem, symlink, backup, systemd or material-review changes**; a missing, denied, stale, public-readable or mismatched record fails closed. Reinstalling the same exact checker revision can proceed without creating a new review. The root-only installer is not a substitute for identity-verified authorization or separately governed production release approval. The installer creates the isolated CCC release, preserves an existing `/var/lib/jason/ccc/ccc.json`, installs/enables the service and timer, and requires the initial service run to complete successfully.

## Failure behavior

CCC fails closed. It never changes provider state, never creates authority for itself, never treats missing evidence as PASS, never converts a failed deterministic result with AI judgment, and never replaces the Last Known Compliant pointer after a non-PASS run.
