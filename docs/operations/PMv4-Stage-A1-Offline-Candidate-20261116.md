# PMv4 Stage A1 — independent shadow release package (source only)

**Status:** Immutable **preproduction** artifact created, not activated or approved. It is NOT a production release or evidence that broader PMv4 is operational.

## Verified starting state — November 16, 2026

- Owner-authenticated A0 three-stage native bootstrap completed with full privileged postflight, under source `8c2064193d74cc41b52369681febbc0a74fa96f7`. Original production LKG remains `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- `/var/lib/jason/pmv4-shadow` has the initial empty `0000000000000000000000000000000000000000` baseline, root-owned control locks and signed decision directory. The initial shadow gateway has **not** been started.
- The existing MCP A0 installer issuer remains enabled, but `JASON_PMV4_OWNER_ISSUER_ENABLED=false`. There is **no** live A1 Owner decision.
- The isolated shadow root still lacks a root-provisioned `approved-manifest.json`, `reviewed-scope.json`, candidate release staging, and exact Owner issuer enablement.
- Independent non-mutating `pmv4_shadow_host_runtime.py inspect` reported healthy production Core, protected release ready and `shadow_promotion_ready=false`; the current non-root inspector cannot establish a held privileged cross-release lock.
- Existing original production runtime/MCP images, production freeze/hold and ticket service remain unchanged.

## Reused release code, not a second approval system

`tools/pmv4_shadow_candidate_packet.py` packages **only eight explicit protected Git source files**, building the already defined `ShadowController` release manifest, scope and byte hashes via existing `pmv4_shadow_release.py`, `pmv4_shadow_ci.py` and the canonical Owner signature serializer. It does **not** sign, stage in the root-owned live control tree, call Docker up, touch ticket data, or grant any release authority. Its output is under the unprivileged fixed `/srv/jason/archive/engineering-artifacts` directory. It refuses an unverified protected-main SHA, an unpinned OCI image ID, an existing/unsafe target, and a modified source blob.

The locally built, disconnected-only *preproduction OCI candidate image* is derived offline from the already present `openclaw:local` base digest `sha256:6fdd46f654a1c4edf3ddc7324ebb5918738a35b3e36809c4a47292b399aa7824`. The new **non-running** image ID is `sha256:779bf783c83cdefad82e34ac99335e2a2c017d8aa5588edb0ed2844a885aa9ed`. The source-only Dockerfile introduces isolation labels and corrects the inherited Docker ENTRYPOINT to `tini -s -- node openclaw.mjs`, so the existing unchanged root-owned Compose `command: [gateway, ...]` invokes the real CLI instead of failing with `gateway: executable not found`. The CLI flags and installed `openclaw` health binary were independently checked read-only. No network calls, model API credentials, source or secret mounts, service restarts, or provider actions were introduced. The earlier unsigned image packet and plan were preserved under a `superseded-unapproved-image-dab111f8` archive name, not silently overwritten. Independently verified running Docker container identities and production freeze/hold hashes were unchanged after the image build.

## Immutable preproduction packet

- Source protected main SHA: `8c2064193d74cc41b52369681febbc0a74fa96f7`.
- Output directory: `/srv/jason/archive/engineering-artifacts/pmv4-a1-8c2064193d74cc41b52369681febbc0a74fa96f7`.
- Bundle SHA256: `ddf5b41143036efbb12afcb2bd27f0c4a74081df562248eba551174f3f48a809`.
- Reviewed scope SHA256: `0ea879291cfd875e0cba79b03ed3963cff95cde74ff8f1d1de39b3da6d4833d2`.
- Release manifest SHA256: `aba7e8e3f54f2a0be6e13a70ba40438fdc7227ba8f5bd8c37c814e0bf832d422`.
- Rollback: **initial empty-shadow baseline**, not the existing production runtime.
- Status: `preproduction_candidate_not_authorized`. There is no production root write or shadow container startup.

## Remaining governed acceptance for A1

1. A separate immutable and reviewed trusted **root A1 packet installer** must stage exactly the agreed manifest, scope and bundle, pin the local OCI digest, validate the live root control tree and lock lineage, and return those objects to original absence if any step fails.
2. Verify the Owner issuer through the existing Entra OAuth + Ed25519 trust, activate only the exact independent shadow release scope, and bind one fresh authenticated Owner approval. No Teams approval required. A0 approval may not be reused.
3. Pass two-sided host health/lock and Ticket Core continuity checks, disconnected shadow OCI runtime healthy startup, no paid AI/model fallback, one-time durable release receipt and exact empty-baseline rollback without touching other Docker projects.
4. Keep the global production freeze, promotion hold, original runtime/MCP and all provider integrations unchanged. Independently verify production functional workflows and no new failed services.
5. After further PMv4 stages are proved, continue B (embedded lock), C (external worker), D (independent JSON Runbook Management), E (PMv3 retirement) and other full-outline requirements. **Do not call PMv4 complete at A1.**

No authorization is requested or consumed by this document or source-only candidate.


## November 16 — real privileged A1 preflight Docker 29 denial and resolution

The Owner ran the exact A1 launcher under a real sudo TTY. Source-only review passed, but the **independent root-only preflight** denied `ShadowReleaseDenied:SHADOW_INSPECT_UNAVAILABLE` *before* any Entra Owner challenge or release mutation. Confirmed no Owner proof, root stage, A1 audit, shadow container, reviewed manifest or gateway token was created; the temporary `/run` executor was safely cleaned.

The cause was the installed A0 Docker adapter's strict older missing-object diagnostic. Docker 29.6.2 emits `error: no such object: jason-pmv4-shadow-gateway` (lowercase) and stdout `[]`, whereas the A0 adapter recognizes only uppercase `No such object:`. An absent, not-yet-created shadow container is the correct initial rollback baseline.

The source adapter now accepts **only the exact shadow-container missing diagnostic** in either known format and exits non-mutating; all daemon outages, permission failures, different container names, wrong exit codes or unrelated stdout still fail closed. Because the A0 adapter copy is already root-trusted and must not be silently modified, A1's independently signed root executor now uses a narrowly pinned Docker 29 runner translating only that exact diagnostic for the existing trusted adapter. This avoids replacing any protected A0 file or weakening its other container isolation, health, ownership, rollback or freeze checks.

The fix passed 123 focused tests and 37 subtests; an independent, unprivileged live Docker readback returned expected empty-shadow baseline. The prior unsigned A1 root release plan was archived with its SHA256; the re-reviewed plan binds executor SHA256 `ea259a6a281d3a04d16e7fe4a8fe7b90a00b78e02fe0c9dbecdadd5ccc1c9e1b` and exact whole-release Owner scope SHA256 `7e1f62de1a10e46db934792967f43e03e778990d2764ea42cbdde1657dc61716`. No Owner proof issued and no production mutations performed.

**Still required:** privileged A1 preflight must pass *all* remaining independent gates, notably the root-only active drift-watchdog allowlist, current source/CI and cross-release lock. Only then may one fresh authenticated Owner exact-action decision authorize the disconnected shadow activation. Real shadow start, health, reversal to original empty baseline and Ticket Core continuity remain unverified until executed. Preserve unrelated production Core/MCP, freeze and hold throughout.
