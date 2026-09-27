# CCC Last Known Compliant Recovery Point

**Status:** Implemented and production-proven 2026-09-27
**Owner:** Jason Governance Authority  
**Applies to:** Constitutional and Compliance Check (CCC) recovery promotion

## Purpose

A successful CCC may promote the exact verified state to Jason's **Last Known Compliant** recovery point. The promotion reuses J-900 recovery-package and offline restore verification rather than creating a second backup architecture.

## Promotion rule

Promotion is fail-closed.

- CCC result must be exactly `PASS`.
- `FAIL`, `NOT PROVEN`, missing status, malformed evidence, revision disagreement, dirty source, recovery-package failure, or restore-verification failure cannot advance the pointer.
- The certified source revision must equal the clean repository `HEAD` used to construct the recovery package.
- The runtime revision in the CCC report must exactly equal the runtime-manifest revision.
- Source revision and runtime revision may differ when the difference is explicitly certified and recorded, for example documentation-only authoritative-main changes after a production runtime build.
- A previous Last Known Compliant pointer remains authoritative unless a new promotion completes successfully.

## Artifacts

Default recovery packages:

`~/Jason-Recovery/CCC/`

Default CCC checkpoints and pointer:

`~/Jason-Evidence/CCC/`

Each promoted checkpoint contains:

- `ccc-report.json`;
- `runtime-manifest.json`;
- `checkpoint-manifest.json` with source/runtime revisions and SHA-256 hashes;
- a reference to the J-900 recovery package and its checksums.

The atomic pointer is:

`~/Jason-Evidence/CCC/last-known-compliant.json`

The recovery package is independently restore-verified before this pointer is replaced.

## Command

Run from the exact clean certified source revision:

```bash
python3 tools/promote_ccc_checkpoint.py \
  --ccc-report /path/to/ccc-report.json \
  --runtime-manifest /path/to/runtime-manifest.json
```

Success reports `CCC_LAST_KNOWN_COMPLIANT=PASS` and the exact checkpoint, source revision, runtime revision, recovery directory, and pointer path.

## Governance

Creating a compliant recovery point does not authorize rollback. Restoring production to a prior checkpoint remains a separately governed operation requiring the applicable identity, approval, impact review, and post-restore verification. Newer audit/evidence history must not be erased merely because production code or configuration is reverted.

## Production acceptance — 2026-09-27

The first Last Known Compliant checkpoint was promoted successfully after fresh verification of the current governed production state.

- checkpoint: `ccc-20260927T110333Z-83e3f6f59565`;
- certified source revision: `83e3f6f59565ae8240428d0e359ac82531b18a64`;
- live runtime revision: `d2aff802be2a052019d25759a5218e5b4a12f622`;
- recovery package: `/home/al/Jason-Recovery/CCC/vccc-20260927T110333Z-83e3f6f59565`;
- checkpoint directory: `/home/al/Jason-Evidence/CCC/ccc-20260927T110333Z-83e3f6f59565`;
- pointer: `/home/al/Jason-Evidence/CCC/last-known-compliant.json`;
- offline restore validation: PASS;
- recovery-package SHA-256 verification: PASS for bundle, source archive, environment record, and release manifest;
- System Registry validation: `valid`;
- systemd failed units: `0`;
- Prometheus targets: `11/11 up`;
- Central Orchestrator authoritative and `direct_provider_access=false`;
- governed provider read smokes: PASS for Autotask, Datto RMM, Datto EDR, DNSFilter, Backup.net, Kyocera KFS, Microsoft Graph, and System Registry.

An earlier seed attempt correctly failed closed because the historical J-900 restore validator referenced retired `tools/assemble_docs.py`. PR #407 replaced that stale step with the current documentation-control validator; no compliant pointer was advanced until the repaired recovery package passed offline restore verification.

## Integration with recurring CCC

TODO-GOV-005 will provide the deterministic recurring CCC runner and configurable monthly scheduling. Its successful terminal step should call this promotion mechanism. Non-PASS CCC outcomes stop before recovery promotion.
