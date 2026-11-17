# Catalog-scoped root installer — independently read-only preflight

**Date:** November 17, 2026. **Status:** SOURCE ONLY — NOT AN INSTALLER, NOT PRODUCTION AUTHORITY, NOT PRODUCTION ELIGIBILITY. No privilege elevation, service restart, Docker mutation, freeze modification, credential switch, grant or provider write.

## Purpose and provenance

AOT needs a narrowly signed root installation that activates existing Jason catalog-only release/rollback controls without deploying unrelated main functionality or modifying PMv4/Ticket Core. Current installed root worker lacks catalog routes, catalog recovery timer is absent and owner approval handoff directory is absent. The existing runtime/MCP remain on original images.

The independent preparatory preflight is `tools/catalog_scoped_root_install_preflight.py`. It verifies staged, exact-protected-source Git bytes and returns an informational list of root targets and a hash-bound requested installer action, **not** an executable installation grant.

## Exact immutable production evidence checked

| Evidence | Verified value |
| --- | --- |
| Protected main | `f0eeb4081346a39b4007e067fbc4ecdfca587c15` |
| Staged unprivileged root-source directory | `/srv/jason/archive/catalog-scope-source-stage-f0eeb408-20261117` |
| 17-file original package SHA256 | `62fe822f10c9abb7d9b01b7d959cdf0204a4c19dc636420e7349103b9b882a15` |
| Installed root worker rollback SHA256 | `f1fdd0fba98950f4fa18b719547fe8f4fa49807c1b08e4424283061ccd235280` |
| Active production freeze SHA256 | `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f` |
| Preview-only catalog release ID | `release-755fa5fe3f75958f` |
| Preview-only catalog manifest SHA256 | `d3438fe90b55704208dfce0a603703756fa856523803ddc5423cbbefaabcb735` |

The package directory inherits Linux setgid (mode 2700) under AOT's shared archive unless explicitly cleared. This was found in the first preflight; the existing staged source-only directory was corrected with `chmod g-s`, verified mode 0700, and preflight then passed. No production path or file was chmod-ed. Future builder work should explicitly clear inherited setgid, but changing the pinned source before the current release would invalidate exact-source admission.

## Source-only acceptance

The checker requires exact main/ref and Git remote, 17 registered paths and Git-identical file blobs, exact manifest/hash, private staging permissions and no root installer already present. It verifies original root-worker digest, Owner public trust pin, production freeze mode and contents, and no root policy/timer/exchange directory. An unexpected difference fails closed.

Live read-only result: `status=ROOT_INSTALL_PREFLIGHT_ONLY_NOT_APPROVED`; `root_install_manifest_sha256=cc56369fae6dde9dc94ec3cfb26eec4d4466d4b65a33af91ac8fdf6e78a2ce55`, `staged_file_count=17`, `production_mutations=false`, `root_installation_authorized=false`. Offline negative/security test cases cover altered source/blob, extra or missing entries, forged approval indicators, symlink/path and stale Git main.

## Real installation still separately required

**Do not run root installation based on this read-only document or on a chat instruction.** A proper installer must independently validate an authenticated one-use exact Owner signature for installation scope, use immutable protected-source bytes, preserve rollback of the old root worker/policy/systemd/host references, install minimal root trust and automatic recovery, and verify actual host postconditions under the existing serialized Production Manager lock and production freeze. It must not introduce a second generic root authority, widen the Owner allowlist, or promote runtime/MCP until a separate signed exact-release offer is approved.

After **separately authorized** root installation, verify root worker and recovery watchdog active, stage the exact catalog offer through the existing native root worker, obtain a fresh authenticated Owner signature, and promote only the two pinned catalog images with tested rollback. Later, separately grant catalog rights and approve the exact inactive no-billing first Service creation from PR #2540. Distinct Service Bundle membership functionality remains separate issue #2539 and PR #2541.

Related: root installation issue #2542, catalog release PR #2538, source-only first write PR #2540.

## Re-attestation after protected main advanced

Protected main advanced via merged PR #2543 (source-only root install plan). A fresh guarded catalog admission returned receipt `f759f516d8f43525dbddecd50945395db184ad1479298e8360f6b0bf1cfd1a8b`. The independent native install plan under current main reported 17 files, installation scope `bc89ed72a00e190978e5c4798f44f141b255460b898f0afa01718b344754ae9f`, and installation plan `fa54e5e7925c35ea6336c84c86b439857c517b197a50b3ad309dcd17a63eb292`. The separate direct staged-file verifier reported the installer-manifest SHA256 recorded above. Both are **unsigned, no-root-mutation evidence only**. No previously computed hash should be reused after protected source changes.
