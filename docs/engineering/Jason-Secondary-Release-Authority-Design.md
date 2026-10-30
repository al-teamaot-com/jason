# Secondary release authority -- offline preflight design (Jason)

**Status: local, unactivated design.** No Release Manager code paths, root
policies, CCC enforcement, release records, production containers, or
QuickBooks connections have been changed by this work.

## Motivation

The existing Release Manager directly invokes `git fetch origin main` and
GitHub check-run queries when preparing/approving/deploying a release.
Suspension or prolonged unavailability of the GitHub hosting account blocks
the entire governed release pipeline. Replacing `origin` with a local branch,
falsifying check records or skipping the GitHub verification is not acceptable.

## Layered source and evidence verification

A portable Git bundle provides repository *bytes*, not authority. A local
test report provides a result, not proof that protected CI completed.

`tools/offline_release_attestation.py` is a standalone **read-only** preflight
that requires all of the following before returning a verification result:

1. An external CI signer whose exact Ed25519 **public key** is already
   pinned to an independent, owner-approved trust-root configuration.
   The verifier never accepts the signing key from the source bundle,
   attestation itself, or an arbitrary user prompt.
2. Fresh, canonical-JSON signed evidence for the expected repository,
   commit SHA, prior rollback SHA, approved secondary source authority,
   authenticated signer identity, and protected-main SHA.
3. Every specifically required CI check named in the existing repository
   policy, with unique run ID, completed status and success conclusion. No
   extra/missing/duplicate checks. Evidence older than 24 hours is rejected.
4. An ordinary Git bundle matching the *signed* SHA-256. The bundle is
   imported into a fresh temporary Git repository without checking out or
   running source. Git must prove that the candidate is an ancestor of the
   signed protected-main SHA, and that the rollback SHA is an ancestor of
   the candidate.
5. A safe report with source/CI preflight details. The result *always* says
   `production_approval=false` and `production_deployed=false`.

The trusted signer and repository identity will need a separate documented
review, issuer-scoped permission, key rotation and revocation procedure.
Cryptographic verification proves the authorized signing key approved the
claims. It cannot itself prove the secondary platform enforced branch
protection, or that its CI environment was isolated. Those are onboarding
acceptance requirements.

## Hosted CI and production bootstrap prerequisites

- AOT administrator sets up an approved independently managed code host
  (e.g., Azure DevOps). Mirror/import the existing repository history,
  restrict writers, enforce protected branch and reviewer policy.
- Create an isolated build agent *outside* Jason production. Review supply
  chain boundaries, dependencies, outbound access, image signing, and
  secret handling. Never store CI signing private keys in the Git repo,
  on Jason's production VM, or alongside the candidate bundle.
- Require independent trusted CI to complete all current required checks,
  produce an exact-SHA attestation and sign with a registered key that has
  been provisioned into the root-owned trust store **through a separately
  authorized bootstrap**.
- Authorize the *change in source authority* as protected-core work. The
  installed Release Manager currently supports only GitHub; this document
  and preflight module do not change that.
- Implement a reviewed, rollback-capable release-authority adapter with
  explicit owner-selected GitHub or secondary authority. The adapter may
  consume preflight results but must **not** equate them with owner approval,
  independent CCC, fresh drift check, baseline alignment, artifact digest,
  preproduction acceptance, the production health gate or rollback.
- Security acceptance: wrong/unknown signer, revoked key, stale report,
  tampered or absent bundle, incomplete checks, altered protected SHA,
  unrelated tenant/repository, or unreachable rollback baseline must
  all stop promotion without any production changes.
- After owner-approved bootstrap, use exact-SHA release approval and the
  independent CCC material review for every required release.
  Keep QuickBooks Sandbox in place through the initial controller stage.
  Production read-profile activation is a **separate** approval/release.
- If the new CI cannot produce trusted evidence, remain blocked instead of
  falling back to unsigned local results.

## Existing October 13 QuickBooks package

A complete source bundle for commit
`97b2d4f3e01edd726e8b15548e56e09f0a072ce1` is retained at
`/srv/jason/archive/offline-release-kits/quickbooks-20261013`, copied from
`/home/al/jason-offline-release-kits/quickbooks-20261013`.
The SHA-256 checks and Git bundle integrity pass. The bundled branch is
**not yet** approved/merged protected main and carries **no signed CI
evidence**. The bundle is therefore a transferable source backup, **not**
eligible for production promotion.

The new offline preflight code is separate from that earlier bundle and
requires a newer commit/bundle after local engineering acceptance.

## Scope, limitations and acceptance

- No requests to Microsoft Graph, Intuit, GitHub, or Azure DevOps are
  performed by the offline preflight.
- The offline preflight imports untrusted bundle bytes through Git.
  Before production use, sandbox the import on an isolated CI agent,
  apply size/time/process limits, ensure no working-tree hooks, and review
  Git/libgit2 or CLI vulnerabilities. No automatic transition currently
  consumes its output.
- Exact signed evidence is only meaningful if the signing key belongs to an
  authenticated, governed CI run; accepting an arbitrary developer-generated
  attestation as CI is forbidden.
- A source bundle *on a different local disk* is not a remote backup.
  Independent encrypted off-host backups and restore drills remain needed.
- User accounting data cannot be read or written by this verifier.
- Revalidation against live services, protected root controls, and the
  installed CCC must occur independently before any later cutover.

**Local engineering tests:** Run

```sh
cd /home/al/jason-worktrees/quickbooks-production-acceptance-20261013
PYTHONPATH=implementation:implementation/runtime_service/src \
  /home/al/projects/jason/.venv/bin/python -m pytest -q \
  tools/tests/test_offline_release_attestation.py
```

These tests exercise Ed25519 signatures, unknown/untrusted signers,
post-signature tampering, missing CI checks, stale timestamps, mismatched
repositories and SHAs, source-bundle checksums and rollback ancestry.
They do not count as externally certified protected CI.
