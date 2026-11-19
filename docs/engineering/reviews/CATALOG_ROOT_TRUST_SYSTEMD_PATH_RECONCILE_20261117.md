# Catalog root trust — exact installed systemd unit path reconciliation

**Source-only corrective engineering. NOT a production installation, Owner approval, release, breaker override or image promotion.**

## Observed production defect (17 November 2026)

The separately authenticated Owner root bootstrap installed the approved 17 source blobs for catalog scoped runtime/MCP release. Root worker SHA256 `55890d6725cc49c2e70743ced3632a79817267764a1dbaa876bdd9e77a5e8e18` and all 17 installed file SHA256s were independently observed to match the reviewed `01ba71c54d9dd0391734b16a92d0b292fc457ae9` plan. Both recovery timers were active/enabled and the original production images and frozen marker were unchanged.

Nevertheless, two root-worker catalog stage requests failed on 17 November with `FileNotFoundError: [Errno 2] No such file or directory: '/usr/local/lib/jason/catalog-scoped-promotion/infrastructure'` (root worker results `cd96f44ab9de49e0998def3bdea53c6f.json` and `6b17b6fd87fb43059449e615adc9e030.json`). The root worker's `_trusted_catalog_scoped_promotion_module` expected both systemd unit sources and their parent directories under the immutable bundle root; the exact `catalog_scoped_root_install_plan.target_for_source()` instead installed those **same two source blobs** at the permanent root-owned `/etc/systemd/system/jason-catalog-scoped-recovery.{service,timer}` paths. This was an internal source-to-installed-path mismatch, not lack of source integrity, missing Owner approval, a provider failure or a need to modify shared Owner allowlists.

## Minimal source correction

The root worker now uses `_catalog_scoped_installed_source_path(trusted, relative)` to map only three fixed source paths outside the bundle: its own root worker file and the two reviewed systemd unit files. All other source files still resolve inside the root-owned immutable bundle. The redundant, never-installed `infrastructure/` bundle directories are removed from its root trust directory list. It continues to verify every required file is root-owned, not a symlink, safe mode, link count, bounded size, and **byte-for-byte equivalent to the Git blob at the exact protected source SHA**. The installed root policy's independent SHA256 checks of both recovery units remain unchanged. No source path is executable because of this mapping.

Security regression tests compare every one of the 17 immutable source paths to the already-reviewed installer destination map and reject absolute or parent-traversal paths. A structural test checks that the protected root loading path uses this mapper while retaining all file trust and SHA checks. These tests are wired into SEC-007. There is no privileged apply path in this PR.

## Separate production desired-state conflict

A different, independently confirmed incident exists at the same time: the four newly installed catalog recovery systemd units are absent from the live frozen desired-state inventory. `jason-production-drift-watchdog.service` is failing and the production breaker has been opened. PR #2552 prepares a **separate one-use Owner-approved** reconciliation to remove those undeclared units for native watchdog recovery, leaving catalog promotion ineligible until an explicitly approved native desired-state release lists and accepts its recovery controls. This path correction does not claim to repair that unrelated global desired-state contract; it must not be deployed to work around the protected breaker.

## Release boundaries and acceptance

Merging this source patch **must not update the live root worker**. A separate exact-SHA, Owner-authenticated root-worker/policy update, with verified original-worker rollback, production lock, frozen marker, active desired-state contract and root-only ledger, is required before the source patch can affect a live catalog stage. Restaging the unsigned offer is only appropriate after the global recovery unit desired-state conflict is independently resolved and the root worker installation's hash-pinned policy matches the exact approved corrective source.

Only then may the team obtain a different signed, one-use runtime/MCP promotion approval and verify the paired-image rollback. A further distinct approval is required before the first inactive/nonbillable Autotask service write/readback using Jason's own service identity. This PR does not authorize a provider write, broaden any identity, restart any production service, disable a breaker, remove the freeze, or promote unrelated PMv4/financial components.
