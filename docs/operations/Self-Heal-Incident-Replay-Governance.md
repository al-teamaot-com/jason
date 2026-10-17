# Self-heal incident replay after source-provider restoration

## Root cause and containment

The v2 self-heal watchdog correlates symptoms into stable root-invariant
families and atomically publishes CURRENT incident paths in
/var/lib/jason/openclaw/self-heal/state.json.

During the October 14 GitHub recovery, the separate SUPPORT worker scanned
the first 100 incident JSON files in the directory. Legacy v1 files had
one unique fingerprint per transient failure/scan combination. The worker
therefore attempted to admit historical evidence as new open SUPPORT issues
when GitHub connectivity resumed.

## Required behavior

- Admit only references in the v2 watchdog state manifest when the state
  is actively repair_required or owner_action_required.
- Require exact 24-character lowercase fingerprint, canonical incident
  path under the self-heal incident directory, matching family, matching
  SUPPORT-AUTO identifier, v2 schema, and repair-required state.
- Deny missing, inconsistent, duplicate or path-traversal records; do not
  fall back to directory scans.
- Healthy/recovered watchdog state must not reactivate old evidence.
- Legacy v1 JSON and already-created GitHub issues stay preserved for
  audit and controlled remediation; never bulk-delete, auto-close, or
  claim detector resolution from cleanup alone.
- The current three operational families observed during the audit were
  production convergence, provider health and ticket admission. All
  require detector rechecks before closure.

## Integration coordination

GitHub PR #1132 modifies the blocked-notification logic in
sync_support_lifecycle_notification() and its early worker tests. This
change modifies the separate load_self_heal_incidents() function and
incident-intake tests. The source hunks do not overlap, but both PRs touch
the same sensitive worker and test files. Keep both changes, rerun
integration checks against the final protected merge SHA, and do not treat
this document as an independent approval of either PR.

## Acceptance

1. Synthetic 125-file legacy spool plus two current v2 incidents produces
   only two current SUPPORT admission candidates, retaining all files.
2. Healthy state admits zero, even with historical files on disk.
3. Bad paths, mismatched fingerprints, duplicate identities and missing
   live records fail closed.
4. Production read-only intake against the October 14 incident directory
   yields only the three v2 state-referenced incidents.
5. Deploy only via approved protected GitHub review, release acceptance,
   rollback and production verification; no direct live worker edits.

This is a repair to issue ingestion, not authorization to modify clients,
run remediations, or suppress health monitoring.
