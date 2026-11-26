# 19-playbook isolated preproduction rehearsal — draft-only

## Section Goal
Independently rehearse immutable JSON registry operation and recovery for all
19 source candidates without connecting to production, changing any live
provider, or staging/activating a JSON version in Jason's production registry.

## Exact source-only execution
On November 19, 2026, `tools/legacy_json_isolated_preprod_acceptance.py`
opened a newly created private, isolated SQLite registry below the
source worktree's ignored `tmp/json-isolated-preprod-validation/` directory.
The script has a fixed output root, refuses any alternate destination or
symlink-backed store, stages all 19 exact immutable candidates as **drafts**,
closes and reopens the registry read-only, and asserts every fingerprint and
state. Repeating the script is idempotent. This is the existing PMv4 JSON
registry implementation, not a replacement registry.

Observed:
- Candidate records: **19**.
- Isolated draft registry generation: **19**.
- Active JSON versions in isolated registry: **0**.
- Production JSON stages/activation/retires: **0**.
- Provider reads/writes: **0**.
- Source authorization boundary: all declared JSON mutations are subsets
  of the corresponding authoritative legacy write capabilities.
- Source-only test: `tests/test_legacy_json_isolated_preprod_acceptance.py`
  checks exact root, idempotency, restart and production-path refusal.
- Run-local machine-readable output:
  `tmp/json-isolated-preprod-validation/isolated-preprod-evidence.json`
  (private, never committed to the public repository).

## What this is NOT
This **does not** establish live provider-connected preproduction acceptance.
The current environment has no approved isolated, real-provider, client-scoped
19-playbook execution suite, action-bound Owner approval receipts, or dedicated
test tickets/devices demonstrated for all source workflows. Approval-bound
mutating JSON steps must never run against arbitrary production customers
or inherit authority merely because source-only tests pass.

The separately verified Jason MCP `validate_json_playbook` non-storing
endpoint accepted all 19 payloads with their canonical source fingerprints.
That proves current deployed validator compatibility, not runtime dispatch,
provider execution, independent health confirmation or legacy parity.

## Remaining independently governed acceptance
For each candidate: exact authenticated service identity and provider/client
scope; source-specific positive/negative/approval/retry/restart/job resolution;
provider-readback and audit; source vs JSON behavior parity; no duplicate
legacy active path; rollback; signed exact approval for any side-effect.
Security log clearing, client notifications, reboots, software cleanup,
endpoint patches, ticket state changes and alert resolution require separate
approved test targets and authority before use.

**Preproduction draft-storage rehearsal: PASS.**
**Live provider-connected preproduction execution: NOT VERIFIED.**
**Fully accepted legacy replacements: 0/19.**
**Production activation / legacy retirement: none.**
