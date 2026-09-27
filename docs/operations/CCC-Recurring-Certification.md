# CCC Recurring Constitutional and Compliance Certification

**Status:** Implemented in source; production activation pending  
**Owner:** Jason Governance Authority  
**Related:** TODO-GOV-005; `CCC-Last-Known-Compliant-Recovery.md`; J-900 Release and Recovery Pipeline

## Purpose

CCC provides a deterministic recurring certification loop for Jason's current production state. It does not grant execution authority and it does not replace the J-002 Constitution, owner review, Central Orchestrator, JKD-001, provider/client boundaries, or J-900 recovery controls.

The default effective cadence is **30 days**. The systemd timer wakes once per day only to determine whether certification is due or whether a material source change requires an out-of-cycle run. `cadence_days` is configured in `/etc/jason/ccc.json`; changing the effective cadence does not require source or unit-file edits.

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
- production file: `/etc/jason/ccc.json`

The installer preserves an existing production configuration rather than replacing it during an upgrade.

## CCC service authority

Live provider canaries use a dedicated non-human JKD-001 identity:

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

Provisioning is explicit and audited by `tools/provision_ccc_authority.py`. The scheduled provider canaries execute through JKD-001 and Central Orchestrator by reusing Jason's governed autonomous observe request path. They do not import MCP and bypass its authentication boundary, and they do not call provider APIs directly.

## Certification checks

When a full CCC run is due, the runner verifies at minimum:

- authoritative `origin/main` revision;
- checker/source currentness for configured governance-sensitive paths;
- source/live-runtime alignment for configured runtime-sensitive paths;
- exact owner review when material-change prefixes have changed since the Last Known Compliant source;
- all nineteen J-002 certification matrix articles remain `PROVEN` and the final 100% certification decision remains present;
- System Registry deterministic validation;
- J-900 release validation including Kernel/CAP-001 tests, documentation-control validation, strict documentation build, and whitespace checks;
- production-equivalent MCP constitutional certification suite;
- zero failed systemd units;
- all configured Prometheus targets healthy;
- current OpenClaw/JKD-001 operational health snapshot is `pass` and fresh;
- `/opt/jason/current` resolves to the exact live MCP runtime revision;
- MCP governance reports `central-orchestrator` and `direct_provider_access=false`;
- all configured governed provider canaries succeed through the dedicated CCC observe identity.

## Material changes and owner review

Configured material paths cause an out-of-cycle CCC run even when the monthly cadence has not expired. If a material change is present, CCC requires `/var/lib/jason/ccc/material-review.json` to approve the **exact current source SHA**. A prior review cannot authorize a later revision.

The owner-review record is created explicitly with:

```bash
python3 tools/record_ccc_material_review.py \
  --source-revision <40-character-sha> \
  --recorded-by person-al \
  --reason "<review rationale>"
```

This preserves the constitutional distinction between deterministic verification and requirements that still need human architecture/governance judgment.

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

When the deployment itself is a material change, supply an owner-review JSON already bound to that exact source SHA. The installer validates and installs the review before the first CCC service start. The installer creates the isolated CCC release, preserves an existing `/etc/jason/ccc.json`, installs/enables the service and timer, and requires the initial service run to complete successfully.

## Failure behavior

CCC fails closed. It never changes provider state, never creates authority for itself, never treats missing evidence as PASS, never converts a failed deterministic result with AI judgment, and never replaces the Last Known Compliant pointer after a non-PASS run.
