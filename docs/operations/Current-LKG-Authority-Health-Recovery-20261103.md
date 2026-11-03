# Current LKG authority-health bootstrap recovery — 2026-11-03

## Incident state

The exact production Last Known Good (LKG) revision is `1b28ddc9863aee563755cb57599cf211ee82ac19`. After the failed production attempt of `891648e99a94db7ed5d17120ef142860ace90650`, runtime, MCP, immutable host release, and Release Manager source were independently observed back on the exact LKG. The release record nevertheless remains failed with `rollback_verified=false`, and the protected production breaker remains open because authority-health evidence is not clean.

The LKG full-integrity wrapper has a 1,800-second bound. Its current workload includes the large orchestration audit database and authority backup/restore proof; the live LKG full-integrity unit exhausted that bound and published explicit failure evidence. Frequent authority health then correctly fails because a recent full-integrity proof is absent. Root drift therefore cannot become clean, and root revalidation cannot close the breaker.

The failed release record is not rewritten. The exact failed release authorization is not reused.

## Recovery boundary

This change adds a narrowly pinned compatibility path to the root-owned host reconciler for only the current exact LKG above and only while the protected circuit breaker is open and the protected LKG manifest still identifies that exact revision.

The recovery path:

1. Reads the two historical LKG health programs from protected Git by exact revision.
2. Requires their fixed SHA-256 identities: wrapper `bbd7aede51986a5caefb5c99ed64b420786fc9b1f8e1aca69e12f65782dbbb56`; operational tool `f5c7c47db4c62268acfb9cb72bcc63d47b3e5378cbcf2839ad620b430c32425a`.
3. Changes exactly one historical wrapper constant from `SOURCE_HEALTH_TIMEOUT_SECONDS = 1800` to `3600` in a root-owned throwaway materialization. The integrity, backup, restore, count, delegation, registry, provider-contact, and failure rules are unchanged.
4. Runs the pinned wrapper as the unprivileged `al` account with `TMPDIR=/srv/jason/archive`. That archive path must remain `al:jason`, mode `2770`.
5. Requires the resulting full-integrity evidence to be a regular non-symlink file owned by `al`, mode `0600`, with `status=pass`, source exit code `0`, no provider contact, no provider credentials, and no failures.
6. Only after that proof does ordinary exact-LKG host reconciliation continue. Existing authority fast-health, systemd result, drift, root revalidation, immutable LKG fingerprint, and breaker gates remain mandatory.

The compatibility health run is bounded to 3,650 seconds. The subsequent host reconcile is bounded to 500 seconds. Their combined 4,150-second maximum remains below the existing 4,500-second root-worker service ceiling.

## Safety properties

- No provider mutation or credential use is introduced.
- No production deployment authority is created.
- No root policy is broadened by this recovery helper.
- No health check, integrity check, backup/restore proof, drift check, or root LKG verification is skipped.
- No arbitrary historical SHA receives the compatibility behavior.
- Changed historical blob hashes, changed timeout source text, changed LKG identity, a different breaker state, an unsafe archive path, a timeout, a nonzero health exit, malformed evidence, or non-PASS evidence all fail closed.
- The original failed release remains historical evidence and is not retroactively changed to a verified rollback.

## Validation

Focused host-reconciler tests cover exact historical source pinning, timeout-only transformation, controlled temporary path, mandatory PASS evidence, and finite recovery budgets. Adjacent host reconciliation, protected root-policy migration, atomic rollback surfaces, root-policy fault paths, and root breaker revalidation suites are also required before integration.

This is source-only recovery engineering. It must not be copied directly into the live root boundary or used to bypass protected source integration, exact-revision release authorization, or PMV3 production controls.
