# PMv4 standalone shadow release — preproduction authority and implementation

**Status: SOURCE ONLY / NO PRODUCTION DEPLOYMENT / FORMAL GOVERNANCE AMENDMENT OUTSTANDING.**

## Objective and decision

Owner direction on 2026-11-11: proceed with a **standalone PMv4 release process**
rather than wait for the troubled PMV3/Teams release path. This is authority to
engineer, test, and prepare the independent *shadow* deployment. It does not
retroactively authorize any specific production SHA, root configuration change,
service restart, provider mutation, freeze override, or unverified Owner decision.

The standalone PMv4 release process MUST comply with the approved Jason Canon,
Operating and Communication Agreements, PMV3's applicable production safety and
exact-revision authority terms, and formal Owner change control. It must not
silently treat the proposed PMv4 single-approval goal as an already ratified
replacement for the current governing production agreement. A separate
project-specific PMv4 shadow-lane authorization/amendment is necessary.

## Proposed independent architecture

- **Dedicated namespace:** only jason-pmv4-shadow; never use PMV3 release
  queues, deployment tools, existing Teams cards, rollback stores, Docker
  Compose project, runtime/MCP images, or production OpenClaw data.
- **Source:** protected GitHub al-teamaot-com/jason main at one exact
  40-character SHA. Fetch fresh *live* API results for protected branch and
  all four required CI workflows. A PR-only passing run or local JSON
  claiming success cannot authorize release.
- **Owner authority:** reuse only the *provider-neutral cryptographic*
  implementation/kernel/signed_owner_release.py verifier. The issuer must
  independently authenticate an AOT Owner via Entra OAuth, never an email,
  Teams message, Owner chat text or locally written approval. Pin the signer
  public key outside the repository in root-owned trust policy. Approval must
  bind **exact candidate SHA, rollback SHA, scope SHA-256, manifest SHA-256,
  freeze SHA-256, release ID, 15-minute expiry and one-use ID**.
- **Scope:** jason-pmv4-shadow alone; read-only/disconnected mode, no
  external ports, no provider-write credentials and no permission changes.
  Protected Ticket Processing is a non-changeable Core service. Component
  manifests, host Compose file and image IDs are pinned. Unknown changes fail closed.
- **Execution:** separate PMv4 lock, root-controlled shadow filesystem,
  immutable candidate bundle, exclusive decision receipt, atomic shadow
  pointer, and scoped Docker Compose project. The trusted image is locally
  present (--pull never) and launched without network, host ports, host
  binds, Docker socket, extra Linux capabilities or production credentials.
- **Acceptance and rollback:** independently verify shadow gateway healthy,
  compare a trusted fresh Ticket Processing Core health baseline/readback,
  verify current pointer, approval receipt and freeze unchanged. On failed
  acceptance, restore only the shadow project and the previous package (or
  the explicit **empty-shadow baseline**). Failed/uncertain rollback
  remains durably blocked for host reconciliation, never reported PASS.

No parallel task scheduler, identity provider, approval store, PMV3
replacement or autonomous release promoter is added by this work.

## Source files and exact boundaries

| Source | Responsibility |
| --- | --- |
| tools/pmv4_shadow_release.py | Independent release transaction, exact proof, journal, rollback |
| tools/pmv4_shadow_ci.py | Live GitHub main and protected CI verifier |
| tools/pmv4_shadow_docker_adapter.py | Shadow project-only container deployment/health/rollback |
| tools/pmv4_shadow_owner_issuer.py | Source-only exact Owner issuer adapter; requires independently verified Entra middleware |
| config/pmv4-shadow/docker-compose.yml | Source-only, disconnected, limited gateway profile |
| tests/test_pmv4_shadow_*.py | Offline positive and fail-closed acceptance |
| .github/workflows/validate.yml | Protected CI regression step |

The existing PMv4 specialist manifest's production_release_controller remains
the **existing deployed** PMV3 value for truthful state reporting. The new
target_shadow_release_controller indicates only planned source authority.

## Initial shadow release — mandatory sequence

1. Verify current PMV3 transaction/root control state and production Ticket
   Processing health. An active or uncertain production transaction is a
   technical noninterference blocker on a shared host, not a reason to
   bypass it. Use a separately allocated host if isolation requires it.
2. Complete source review, protected checks, distinct OCI image build and
   prod-equivalent offline startup/recovery tests. Merge candidate to protected
   main only through ordinary authorized source governance.
3. After separately approved bootstrap, provision the private shadow root
   /var/lib/jason/pmv4-shadow, independent Docker project,
   reviewed scope/manifest/rollback, local pinned image, shadow freeze and
   root-owned public trust policy. Provision a distinct gateway token without
   printing or checking any secret into GitHub.
4. Connect an independent trusted **Entra Owner approval issuer** for this
   exact PMv4 release namespace. The existing PMV3 issuer cannot simply be
   assumed to support PMv4 release identifiers. Issue a one-use decision
   ONLY after the authenticated Owner approves the *actual immutable*
   shadow candidate, scope, rollback and manifest.
5. A reviewed root-owned installer connects the immutable callbacks
   (protected_main_ci_verified, shadow Docker activator, trusted fresh
   Ticket Processing Core continuity probe), then calls
   ShadowController.promote. It cannot obtain callback logic from the
   untrusted candidate bundle.
6. Independently read back shadow startup, Core no-regression, one-time
   release receipt, frozen bytes, and preauthorized rollback. Retain
   isolated logs/evidence. No post-release provider or ticket writes.
7. Expand to subscription-backed model dispatch or provider reads only
   under separate scoped authority and acceptance.

## Bootstrap and external dependencies not yet satisfied

- **No approved root trust/key provisioning for PMv4.** A public key
  provisioned for another release lane cannot be copied unilaterally.
- **No live separately authenticated Entra Owner PMv4 issuer.** A source-only
  issuer adapter now reads root-reviewed shadow scope and signs the same exact
  Entra Owner release proof ONLY after a trusted OAuth JWT-verifier callback
  and exact Owner consent callback return valid evidence. The isolated tests
  use synthetic callbacks and an ephemeral key; no actual Entra bearer or
  browser consent route, audience registration or signer is provisioned.
  This source code alone cannot mint a production-valid Owner decision.
- **No installed root-owned host adapter or official OCI release artifact.**
  DockerShadowAdapter is tested with a fake command runner, not yet activated.
- **No trusted live Ticket Processing continuity probe wired to the
  independent host runner.** Passing source tests does not establish Core
  health or protect against a production regression.
- **No end-to-end independent shadow gateway startup/restart and automatic
  interrupted-agent recovery acceptance.** A restricted isolated CLI
  container returned OpenClaw 2026.7.1 successfully. That is NOT a
  successful gateway deployment or working model session.
- **No formal PMv4 shadow production-lane amendment or exact-release approval.**
  Owner permission for engineering is not the exact production authorization
  required once candidate SHA and rollback are known.
- Current PMV3 ticket worker was recently observed STALLED; this baseline
  defect requires fresh provider readback before release acceptance.

## What the preproduction tests prove

Source tests generate ephemeral private keys only in disposable temporary
directories and simulate authenticated proof issuance. The tests now include
the complete synthetic issuer -> signature -> standalone release transaction.
They prove the deterministic verifier enforces signature, expiry, scope and
replay binding; they do NOT authenticate the Owner in a live session. Synthetic Docker
runners assert fixed commands, project isolation, rollback and health gates.
No live gateway restart, production Docker Compose activation, provider
action, real token, production public/private signer or root change has
been attempted by these source changes.

## Proposed governance amendment — NOT APPROVED OR EFFECTIVE

AOT may adopt the PMv4 shadow release lane as an independently managed
component while retaining strict exact-release Owner authority, root-owned
trust, protected-source provenance, one transaction per shadow service,
immutable evidence, freeze protection, independent Core health and rollback.
Teams routing and the PMV3 *software release pipeline* shall not be required
for this isolated PMv4 component, provided the independent Entra issuer and
all equivalent release controls are independently tested and formally
approved. This does not permit production changes affecting shared root
services, global identity providers, active endpoints or Ticket Processing
without their separate applicable scope authorization.

**This document itself is not an Owner approval or executable grant.**
