# Catalog-scoped root installer — independently read-only preflight

**Date:** November 17, 2026. **Status:** SOURCE ONLY — NOT AN INSTALLER, NOT PRODUCTION AUTHORITY, NOT PRODUCTION ELIGIBILITY. No privilege elevation, service restart, Docker mutation, freeze modification, credential switch, grant or provider write.

## Purpose and provenance

AOT needs a narrowly signed root installation that activates existing Jason catalog-only release/rollback controls without deploying unrelated main functionality or modifying PMv4/Ticket Core. Current installed root worker lacks catalog routes, catalog recovery timer is absent and owner approval handoff directory is absent. The existing runtime/MCP remain on original images.

The independent preparatory preflight is `tools/catalog_scoped_root_install_preflight.py`. It verifies staged, exact-protected-source Git bytes and returns an informational list of root targets and a hash-bound requested installer action, **not** an executable installation grant.

## Exact immutable production evidence checked

| Evidence | Verified value |
| --- | --- |
| Protected main | `1b804ea6cff8efedc4f9b29b3dddaf45e86e8f82` |
| Staged unprivileged root-source directory | `/srv/jason/archive/catalog-scope-source-stage-1b804ea6-20261117` |
| 17-file original package SHA256 | `c8da8db18a18d746fca3fbc70379c1796d57858e15f6700c3ad463cd5954dc12` |
| Installed root worker rollback SHA256 | `f1fdd0fba98950f4fa18b719547fe8f4fa49807c1b08e4424283061ccd235280` |
| Active production freeze SHA256 | `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f` |
| Preview-only catalog release ID | `release-755fa5fe3f75958f` |
| Preview-only catalog manifest SHA256 | `4712f94dc35e1d6781fe6e8c02b57278da9bd0f10ebedaea130c2934f1b5f45b` |

The package directory inherits Linux setgid (mode 2700) under AOT's shared archive unless explicitly cleared. This was found in the first preflight; the existing staged source-only directory was corrected with `chmod g-s`, verified mode 0700, and preflight then passed. No production path or file was chmod-ed. Future builder work should explicitly clear inherited setgid, but changing the pinned source before the current release would invalidate exact-source admission.

## Source-only acceptance

The checker requires exact main/ref and Git remote, 17 registered paths and Git-identical file blobs, exact manifest/hash, private staging permissions and no root installer already present. It verifies original root-worker digest, Owner public trust pin, production freeze mode and contents, and no root policy/timer/exchange directory. An unexpected difference fails closed.

Live read-only result: `status=ROOT_INSTALL_PREFLIGHT_ONLY_NOT_APPROVED`; `root_install_manifest_sha256=00e26ab2101fb7221be5cba06424262efcc9b2056e3b3cea047d12ba932b6445`, `staged_file_count=17`, `production_mutations=false`, `root_installation_authorized=false`. Offline negative/security test cases cover altered source/blob, extra or missing entries, forged approval indicators, symlink/path and stale Git main.

## Real installation still separately required

**Do not run root installation based on this read-only document or on a chat instruction.** A proper installer must independently validate an authenticated one-use exact Owner signature for installation scope, use immutable protected-source bytes, preserve rollback of the old root worker/policy/systemd/host references, install minimal root trust and automatic recovery, and verify actual host postconditions under the existing serialized Production Manager lock and production freeze. It must not introduce a second generic root authority, widen the Owner allowlist, or promote runtime/MCP until a separate signed exact-release offer is approved.

After **separately authorized** root installation, verify root worker and recovery watchdog active, stage the exact catalog offer through the existing native root worker, obtain a fresh authenticated Owner signature, and promote only the two pinned catalog images with tested rollback. Later, separately grant catalog rights and approve the exact inactive no-billing first Service creation from PR #2540. Distinct Service Bundle membership functionality remains separate issue #2539 and PR #2541.

Related: root installation issue #2542, catalog release PR #2538, source-only first write PR #2540.
