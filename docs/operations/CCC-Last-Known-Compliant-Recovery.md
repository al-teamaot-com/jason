# CCC Last Known Compliant Recovery Point

**Status:** Implemented foundation; production seed acceptance pending  
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

## Integration with recurring CCC

TODO-GOV-005 will provide the deterministic recurring CCC runner and configurable monthly scheduling. Its successful terminal step should call this promotion mechanism. Non-PASS CCC outcomes stop before recovery promotion.
