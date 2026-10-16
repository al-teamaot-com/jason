# Bootstrap required Azure PR validation during GitHub suspension

This is an isolated, **nonproduction** Azure PR bootstrap. It contains the
reusable read-only Azure PR documentation and overlap checks, their synthetic
regressions, and the YAML registered as Azure pipeline ID 5.

## Why needed

Azure main at cached GitHub SHA e3b80f80 does not contain this pipeline YAML
or its implementation. The mandatory build policy therefore cannot reliably
run for QuickBooks PR #2 or SharePoint PR #3, whose heads also lack those
files. Azure remains a temporary standby and GitHub history is not known
fresh; this change MUST NOT change the canonical source or deploy production.

## Promotion sequence

1. Keep this candidate as a separate PR to Azure main. It must be independently
   reviewed; never self-approve or use bypass permissions.
2. Validate the exact candidate merge commit through required Azure PR
   policy build ID 5 and a minimum of one independent reviewer. Check comment
   resolution and no prohibited Azure provider writes.
3. After an authorized merge, fetch verified Azure main; reconcile PR #2 and
   #3 with current main; re-run the exact-SHA connector CI and PR gate.
4. Retain the existing Production Manager PR #4 draft. Reconcile overlaps
   explicitly; do not imply release parity is complete.
5. No production cutover until separately approved single-writer source
   authority, mapped complete required release checks, rollback and independent
   GitHub reconciliation are established.

## Security

Only the Azure job-scoped System.AccessToken is used for read-only PR
verification in hosted CI. No host private keys or client secrets are
uploaded. No Azure branch policy, reviewer rule, release gate, runtime
configuration, accounting or Microsoft Graph tenant setting is changed
by this commit. All operations remain fail-closed.
