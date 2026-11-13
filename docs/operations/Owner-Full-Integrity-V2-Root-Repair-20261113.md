# Owner Full SQLite Integrity V2 Root Repair — Source-Only Release Gate

**Status:** source-only engineering and disposable acceptance. **NO production root installation, full scan or breaker reset is authorized by this PR.**

## 1. Root cause and non-negotiable controls

On November 12, 2026, the **first** Owner-signed v1 root recovery completed a genuine full integrity proof. All four databases and the full authority backup/restore passed; the immutable root one-shot ledger was consumed correctly. A repeated `--execute` is prohibited and correctly returns `ONE_SHOT_ALREADY_CONSUMED`. The normal scheduled full-integrity service still ran immutable production LKG `d1b8c196dadd4b672ec8ba47075f27bb61c98d63` with its 3,600-second child bound and 3,900-second service bound. Its next run on November 13 timed out, the fast health emergency overlay had expired, and the root drift watchdog opened the release breaker.

PR #2463, merged as `95832507e6e5f804f092cb5d3ebdea90ba1a49bf`, fixes *source only*. It starts the orchestration-audit FULL SQLite integrity proof concurrently with the unchanged other FULL checks and backup/restore. All checks must succeed before PASS. It retains strict 5,400-second child and 5,700-second outer bounds, no quick-check, no expired health exception, no service bypass and no provider writes.

## 2. Fixed, isolated health-only production scope

Source anchor: `95832507e6e5f804f092cb5d3ebdea90ba1a49bf`.

Prepared (not installed) immutable source bundle:
`/srv/jason/archive/owner-full-integrity-v2-repair-source-95832507e6e5f804f092cb5d3ebdea90ba1a49bf.tar`
SHA-256 `f39065a9c98da1fd8900c93f41965b84125129507b527d1e3287ef68e3e5c6d0`.

Prepared exact scope manifest:
`/srv/jason/archive/owner-full-integrity-v2-repair-manifest-95832507e6e5f804f092cb5d3ebdea90ba1a49bf.json`
SHA-256 `c05bed1594d4eec79a47e02ec2a4c677f5772bc9ab92f173ad574708b7fcdf63`.
Approval scope SHA-256 `8267a53e7c532125a8cf8df316c1f71da6eecdb7c8e34536c298119816e483fe`.

Exactly **three newly installed objects**, all root-owned and immutable:

- `/usr/local/lib/jason/authority-health-v2-95832507e6e5/openclaw_authority_health_snapshot.py` (0555)
- `/usr/local/lib/jason/authority-health-v2-95832507e6e5/openclaw_authority_operational_health.py` (0555)
- `/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/91-owner-full-proof-v2.conf` (0644)

The drop-in switches only the existing full-integrity one-shot to those root-owned bytes; sets `TimeoutStartSec=5700`, `Nice=19` and `IOSchedulingClass=idle`. The original unit and daily timer remain installed. No runtime, MCP, ticket worker, provider service, model component, scheduler, networking or credentials are changed.

Only **after a real fresh full PASS** may the action remove the **exact byte-pinned expired** `91-owner-emergency-full-proof-degraded.conf` fast-health overlay, regenerate normal fast-health evidence, and request independent native root drift/breaker revalidation. Never hide or clear the failed health service before the real proof. Revalidation must see at least three separately dated root drift PASS observations and must use existing root-controlled transitions, not a direct breaker JSON edit.

## 3. Separate governed Owner exact-action gate

Source implementation:
`tools/owner_full_integrity_v2_root_repair.py` and its exact
`config/owner-full-integrity-v2-repair-policy.json`.

The root script is **inert in Git**, refuses production execution outside its exact root-owned installed path `/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py` under isolated `python3 -I`, and requires a root-owned hash-pinned policy and separate root-owned empty **new** audit ledger under `/etc/jason-owner-release/owner-full-integrity-v2-repair-ledger`. Never modify or reset the **consumed v1** audit ledger or signed policy.

The v2 operation demands:

1. Independent exact-source and GitHub CI acceptance plus Owner approval for the **new** specific source-only root helper/policy.
2. A *separate* Owner-authenticated production health-repair authorization (NOT the previously approved Stage A0 six-file trust installation).
3. Previously installed verified source bytes at the exact root path, root-owned hash-pinned policy and empty ledger. The root code must independently verify immutable byte hashes of its executable, existing pinned Owner OAuth verifier, pinned Ed25519 signer verifier, original systemd units/expired override, exact V2 bundle and manifest.
4. Fresh Entra Owner device-flow authentication, explicit exact operation confirmation, root-pinned Ed25519 private/public key match, a 15-minute exact-release signed proof binding source, rollback LKG, scope, manifest and unchanged freeze. Audit one-use approval claimed **before** the first systemd/root-source write.
5. Original runtime/MCP image IDs, source labels and healthy runtime; PMv4 issuer OFF; exact production LKG, freeze and promotion hold; production breaker OPEN for only the observed authority-health timeout, no unrelated drift; full service not concurrently active; original reviewed target paths empty; existing native transaction lock.
6. Bounded, low-priority full integrity check through the existing dedicated systemd oneshot. Validate four FULL SQLite checks, exact backup and restored integrity, counts, key registry, delegation state, empty failure set and provider-free evidence. A timeout, incomplete record, partial scan or mismatch is FAIL, never PASS.
7. Only then restore canonical five-minute health; verify it PASS; observe distinct independent root drift PASS samples and request the **existing native** breaker revalidation. No direct mutation of the protected control JSON.
8. Verify the original MCP and runtime identity, production freeze, hold, no ticket changes and the new source/service exact hash state before marking completion. On failure retain OPEN breaker and fail closed; remove only verified transaction-created source files if a full PASS was **not** achieved. Preserve any foreign/new inodes for human review.

No external release/Owner approval is reusable across the consumed v1 action, this new health-repair action and the later Stage A0 root trust/issuer/sparse source/install actions.

## 4. Source-only acceptance

- Local expanded full authority and recovery regression suite + V2 staged installer checks.
- Synthetic Ed25519 exact proof with changed scope rejection.
- Source-archive literal metadata/UID0/mode/hash/path/three-object strict inventory validation.
- Disposable `/tmp` root tree staging/readback/rollback, interrupted operation and unreviewed file/tampering denial.
- Independent read-only Docker `--network none --read-only --tmpfs /tmp` acceptance of the exact V2 bundle: exact install, verified rollback to absence, partial failure recovery, foreign-object refusal, archive-tamper denial; zero writable host bind mounts.
- All repository-required CI/security jobs must pass on the exact reviewed PR SHA.
- This does **not** prove the long full scan will finish on production-sized databases. Production release approval must acknowledge up to 95 minutes of low-priority checker activity, original rollback LKG, and the real hard timeout.

## 5. No-production deployment status and operator boundary

Current production LKG:
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
MCP image:
`sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
Runtime image:
`sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
Freeze SHA-256:
`bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`
Promotion hold SHA-256:
`11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0`.

Current host remote-command channel does **not** permit `sudo`. Do not switch to another privileged channel, cron, SSH automation or service invocation to bypass that boundary. After separate explicit Owner authorization, the Owner must enter an authenticated local root session. The source-only merge and engineering preparations do not grant root installation or a 95-minute production scan.

**Important:** This isolated V2 health operation is NOT the existing PMv4 Stage A0 source-only bootstrap PR #2482 and NOT the already authorized but blocked Stage A0 root trust six-file installation. Resume Stage A0 only after actual root health PASS, drift PASS and independently CLOSED breaker.

## 6. Disposition

**Ready for source review:** exact helper/policy/tests/CI on a separate branch.
**Not production ready:** new trusted root executable/policy/ledger absent; exact Owner production health repair authorization absent; current genuine full proof stale/failed; protected breaker OPEN.
**Needed from Owner:** First exact source-only merge approval after review. Later, a new exact-action Owner production health repair approval and an authorized local root session. Nothing in this source PR relaxes any production safety control.
