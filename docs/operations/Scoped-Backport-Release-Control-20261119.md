# Project Jason — scoped-backport release-control engineering

**Lifecycle:** Source-only protected Production Manager extension. This document is
not an Owner-signed exact production release and does not activate an endpoint
connector. Its scope is the approved Entra group-management release-control
preparation on 2026-11-19.

## Why

The live runtime/MCP and protected PMv4 Ticket Processing Core must not inherit
hundreds of unrelated protected-main source changes merely to activate an
already reviewed Entra group-management implementation. Native Release Manager
correctly rejects a candidate not reachable from protected main. The
scoped-backport path is a separate **source-admission proof**, not a relaxation
of the general main-only release or production freeze.

## Exact AOT group pilot snapshot

- Frozen source candidate: `87dfd07ae67d2d9994c029184bd39ebab5baebbf`
- Verified running LKG source: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
- Originally reviewed group feature: `7498c0968afb52a8d7506f9dc8ad1fd981ef35e5`
- Candidate branch: `refs/heads/prep/m365-lkg-backport-20261119`
- Full LKG-to-candidate binary scope SHA256:
  `49e9c90b3e0336c9f2e42b20f63dddf237ce500540d5dae3e8e77e4e91190ebb`
- Changed-file scope: **43** exact source paths
- Candidate runtime image:
  `sha256:b714a109886cb866653f54d42cd672ed36193d85eb67fc4fd4e7fcd7d62e005c`
- Candidate MCP image:
  `sha256:1b62fc978bb772e65caf549aab8304872970a31b715560b2288026828172cb9b`
- Actual rollback runtime image:
  `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
- Actual rollback MCP image:
  `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
- Observed production freeze SHA256:
  `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`
- Proposed deterministic release identifier:
  `release-87dfd07ae67d2d99` — **NOT a native release record**.

Source-bound manifest: `config/scoped-backport-m365-release.json`.
This manifest includes explicit allowed file paths, reviewed provider source,
tenant/client, distinct candidate and rollback image IDs, protected services,
and the four read-only OpenBao AppRole mount destinations.

## Controls that are mandatory for any actual release

1. Protected GitHub main must publish this source-admission code and manifest.
   Load exact manifest bytes with `git show <verified main SHA>:...`, not a
   worktree. Check the live remote main SHA and candidate branch SHA again
   immediately before mutation. Both source and candidate must remain exact.
2. The root-installed native handler must be **separately approved, source
   pinned, immutable, and audited**. It must not execute an untrusted worktree
   or treat an al-owned request as Owner authority. No such handler is yet
   installed for this profile.
3. Native CI including governed security regressions, staging image IDs,
   runtime/MCP integration, the four AppRole credential mounts, Tenant AOT
   boundary readback, and ticket/PMv4 continuity must pass.
4. The existing root-owned control bridge must prove closed breaker, clean
   fresh drift and the exact unchanged freeze. Worker quiescence must hold.
5. The authenticated Entra Owner must supply one fresh, signed, one-use exact
   release decision bound to candidate SHA, rollback SHA, full scope SHA256,
   manifest SHA256, freeze SHA256 and release ID. Teams is not mandatory.
6. Only the privileged native release host may replace `jason-runtime` and
   `jason-mcp-pilot` under the serialized production lock, preserving all
   other protected containers and source. It must retain the actual LKG
   rollback pair by exact ID rather than assume the shared
   `rollback-current` tags refer to the running baseline.
7. Production readback, live capability registration, service health,
   protected Ticket Core continuity, and rollback-on-error are mandatory.
8. Graph group-creation and membership-add require **separate** exact-action
   approval and provider readback after the release. This release cannot
   authorize a Graph POST.

## Implemented source engineering

- `tools/scoped_backport_release.py`: strict source manifest and immutable
  snapshot admission, explicit low-collateral allowlist, signed Owner proof
  check, one-use consume, protected-service canaries, and paired rollback
  protocol. It cannot mutate production by itself.
- `tools/scoped_backport_docker_rehearsal.py`: genuine isolated Docker
  failure-injection and pair-restoration test with no network, mounts, or
  production-container changes, using UUID-scoped names.
- `tools/scoped_backport_release_request.py`: low-privilege strictly typed
  stage/promote/recover requests, which are denied unless a separately
  root-installed and hash-attested worker is present. The request has no
  Owner decision and is not a production eligible record.
- `tools/tests/test_scoped_backport_release_request.py`: validate the
  uninstalled default, spoofed policy denial, exact source/offer bindings,
  authenticated root worker trust requirement, replay and spool controls.
- `tools/tests/test_scoped_backport_release.py`: negative/positive tests
  for path, tenant, image and Owner-scope drift, stale main, signed approval,
  replay denial, fail-before-mutation, partial promotion, paired rollback,
  breaker escalation and freeze restoration.
- `tools/release_manager_host_runner.py scoped-backport-admit
  --trusted-main-sha <EXACT_SHA>`: new read-only native entrypoint.
  It produces a scoped source offer only once the manifest is actually
  present in verified protected main. It **does not** create a
  production-eligible record or submit approval.
- `tools/release_manager_host_runner.py scoped-backport-{stage,promote,recover}`
  are fail-closed typed submission routes only. They always verify the
  protected-main source before even looking for the independent root handler.
  No root handler is currently installed, so all three refuse to queue a
  request in production. They do not create a release or Owner decision.
- Existing `create`, `prepare`, `preprod`, `approve`, `promote`,
  `rollback-release`, catalog-scoped, and production worker paths remain
  unchanged. The ordinary main-only check is intact.

## Test evidence and current limits

- Source/Owner/rollback and typed-request core: **53 tests passed**,
  including deliberately failed second component, rollback failure/breaker,
  exact root trust, forged request denial and spool replay paths.
- Actual isolated Docker rehearsal: `isolated_docker_rollback_rehearsal_pass`.
  The deliberately failed second component restored the first to the exact
  baseline image; both staged candidate components were then created and
  reverted, leaving all original production container IDs unchanged.
- Private host evidence:
  `/home/al/.local/share/jason/scoped-backport-evidence/m365-20261119-87dfd07-rollback.json`.
- The Owner-authorized four-file AppRole access projection was independently
  evidenced by a root-owned mode-0600 receipt.
- The root-published production control readback returned breaker
  `closed`, drift `pass`, no problems at the time inspected.
- No production deployment, Entra mutation, root installer or root
  handler has been performed by this source-only change.

**Release admission is still prohibited until an exact source-attested root
handler is independently installed and native preproduction, root rollback,
Owner cryptographic approval, and the actual native release record all pass.**
Do not call `approve_release_candidate` for the proposed identifier as if it
were a production-eligible record. It is not.

## Critical native Owner approval boundary

The already deployed `approve_release_candidate` MCP tool reads an actual
`state_root/records/release-*.json` with `state=production_eligible`, an
exact `release_manifest`, and an exact `manual_scope_review`. It will
reject a backport for which no native record exists. Merely constructing
the deterministic ID does not satisfy its signed approval requirements.

An externally fabricated `production_eligible` record would also be unsafe:
the existing ordinary promotion consumer could mistake it for a full-main
release. The dedicated scoped root consumer must first be installed and
must integrate a release-kind-specific dispatcher and rollback so ordinary
`promote-eligible` cannot consume this transaction. Until that is proven,
the native exact-SHA approval cannot legitimately be submitted.

The approved engineering scope does **not** authorize bypassing these
existing release-control mechanisms. Root installation, host-pinned
signed exact-action approval, release record creation, and a real native
release transaction remain separate concrete work and are not represented
as complete in this packet.


## Native host and one-time installation package — not installed

The separate source-only native implementation now includes:

- `tools/scoped_backport_native_host.py`: an independently root-installed
  host requiring its OWN protected code SHA attestation, fresh protected
  main/source/CI gates, AppRole mode and receipt verification, breaker and
  drift readback, exact image IDs, production transaction lock and freeze,
  signed one-use Owner proof, protected worker continuity, and paired rollback.
- `tools/scoped_backport_native_root.py`: bounded typed request consumer
  with root-private stage eligibility; it refuses to promote without an
  independently signed exact release proof. No ordinary Release Manager
  `production_eligible` record is fabricated or delegated to the
  general `promote-eligible` auto-runner.
- `tools/scoped_backport_native_recovery.py`: separate source-bound root
  watchdog which opens the protected circuit breaker on an interrupted
  transaction and restores the exact LKG image pair and original freeze
  evidence. It never auto-closes the breaker or reattempts a provider write.
- `tools/scoped_backport_owner_local_approval.py`: the already installed
  root-owned AOT Entra JWT verifier and existing service Ed25519 signer are
  reused, after a fresh Owner device-code sign-in and one affirmative
  exact-scope confirmation. This issues a bounded one-use signed release proof
  rather than treating a chat statement as a bearer token.
- `tools/scoped_backport_root_install.py`: one-time root installation
  bootstrap that refuses dirty/unpublished/non-main source, checks exact
  images, freeze, breaker, drift, four-file AppRole receipt, and fresh Entra
  Owner approval before copying only the reviewed release-control files.
  The install contains an exact-content partial-install rollback path.
- `infrastructure/scoped-backport-release/`: dedicated request path/service
  plus one-minute recovery timer/service. These are source-only until a
  local authenticated and audited exact-SHA root bootstrap.
- Associated native host, worker, recovery, installer and Owner approval
  unit tests validate fail-closed behavior. Real production root staging,
  exact-scope approval and live rollback have NOT occurred yet.

### Intended governed sequence

1. Complete GitHub security/CI review and merge the root installation source
   to protected main; do not rewrite main history or alter production freeze.
2. Create a clean exact-main worktree for the installer, check the immutable
   root package and its install-scope SHA256, and obtain one authenticated
   local `al` sudo + fresh AOT Entra Owner exact-action approval. Do not send
   a password, OAuth token or private signer through ChatGPT.
3. Verify root-installed source digest policy, both systemd listeners active,
   protected service continuity, and unchanged freeze after root bootstrap.
4. Read-only scope admission with the new `scoped-backport-admit`; submit the
   exact `scoped-backport-stage` request to the root-pinned request worker.
   Obtain a root-origin scoped eligibility receipt after exact source,
   credential, image, rollback and preflight evidence.
5. Only then run the installed local Owner OAuth exact release approval, which
   produces a one-use signed proof. The production transaction requires a
   separately queued exact promote request and fresh release controls.
6. For actual promotion, root must serially replace only runtime and MCP,
   preserve Ticket Core/Shadow Gateway, enforce new group AppRole binds and
   validate both image revisions/health and live group registrations. Any
   failure triggers exact paired rollback and freeze restoration; unresolved
   rollback opens the breaker. Graph POST actions require separate approvals.

**Current status:** production release-control root installation NOT present,
scoped native release ID NOT created, scoped Owner signing NOT completed, and
Entra group capabilities NOT activated. All newly added code and systemd
definitions are engineering artifacts until a protected-main release is
approved and installed; no sudo or provider action is invoked by this packet.

## GitHub CI-reviewed source identity versus protected-main integration

The native root installer deliberately binds **two** immutable identities:

the latest protected-main commit passed as `--source-sha`, and the PR commit
that received the required GitHub checks passed as `--reviewed-ci-sha`.
Both must be full 40-digit commit SHAs. Every installed source file and unit
is compared byte-for-byte across those two commits and against the clean
local protected-main worktree; a squash or merge commit that modifies any
reviewed root source will fail closed. The installer checks the five named
GitHub CI/security signals on the reviewed commit and records both identities
in its mode-0600 root installation policy/audit ledger. The root installer
will not rely on unrelated CI statuses from a busy protected-main merge commit.

The installer must run only after the native source has been reviewed and
merged to protected main, a fresh, exact installation scope has passed
`--check`, and an authenticated local `al` sudo plus fresh signed Entra
Owner decision has been independently verified. The installation itself
never approves or promotes a candidate Entra release.
