# PMv4 Stage A0 — isolated bootstrap release (source-only)

**Authority:** Owner authorized the release-control engineering and nonproduction
testing on November 13, 2026. **No production deployment, service replacement,
root code installation, freeze/hold change, or standing authority was approved.**
This packet is not a production release approval. GitHub issue #2481 tracks the
existing whole-revision release-path blocker.

## Existing operational baseline

- Protected main at the start of this work: `fd2343cf367ea63199418685ff7299889cd50063`.
- Production last-known-good: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Active MCP image: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`.
- Active runtime image: `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`.
- Protected freeze SHA-256: `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.
- Running MCP **already contains** `authorize_pmv4_stage_a0_install` and
  `pmv4_stage_a0_owner_issuer`, but `JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false`.
- The native root reconciler recognizes the exact signed A0 action, but requires
  a new root-owned immutable source tree for the exact protected-main SHA.
- Full-current-main native preproduction passed, but manual release impact returned
  `BLOCKED_SCOPE` (79 files/14 commits). An older three-file release was rejected
  by JES-005 protected-history checks and the exact-candidate-controller gate.
  **Neither must be weakened or silently waived.**

## Compartment 1 — Same-image issuer activation

`tools/pmv4_stage_a0_issuer_activation.py` is a fixed-action, one-use **future
root-installed** control. It is not self-installing and its `--check-only` option
cannot change host state. Any later `--execute` is refused unless the file is
installed at its exact root-owned protected path, launched through isolated Python
under root, and matches a separately approved root-owned policy.

At activation time it independently requires:

1. Root-owned code and policy hashes, trusted existing OAuth verifier/deployer,
   pinned Ed25519 Owner public trust and private-key identity.
2. Fresh signed Entra OAuth Owner identity and exact-action Ed25519 proof with
   15-minute expiry, one-release scope digest and source/freeze binding.
3. Production revision/images, current protected freeze and promotion hold, root
   breaker CLOSED, fresh drift PASS, original readonly signer mount, and original
   hardened MCP shape.
4. Existing PMv3 production transaction lock; one-use audit claimed **before**
   any MCP mutation.
5. The *same* MCP image ID and source revision, with **only**
   `JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false -> true`; no application images,
   bindings, provider credentials, networks, security settings or ticket runtime
   may change.
6. Native container replacement health and independent post-readback of exact
   image, mounts, environment, user, labels, networks, hardening, freeze, hold
   and unchanged runtime container identity. A mismatch triggers restoration
   of the original container when its identity is independently proven.

The installer is an **inert source artifact** until a later, separately approved
root installation places the code and exact policy in the OS trust boundary.
That initial root installation is NOT supplied or approved by this PR. An
operator-owned script, mutable checkout, user-provided policy, or chat approval
cannot be treated as an installed trusted root executable.

## Compartment 2 — Sparse immutable Stage A0 source package

`tools/pmv4_stage_a0_sparse_source.py` creates a reproducible archive from
the exact Git blobs of the **current protected-main SHA**. It accepts no
caller-specified source globs. Only the union of existing
`pmv4_stage_a_packet.BUNDLE_FILES` and
`ROOT_STAGE_A_REQUIRED_SOURCES` is admitted (13 fixed source files at
preparation). Archive objects are ordinary files and directories with fixed
UID 0, GID 0, modes, epoch-zero mtimes, strict canonical paths, byte hashes
and no symlinks, device nodes, hard links, or extra objects.

Example, **unprivileged and nonproduction only** after the source is merged
and the final current protected-main SHA is independently established:

```bash
cd /path/to/clean/pinned/jason
PYTHONPATH=.:implementation python3 -m tools.pmv4_stage_a0_sparse_source \
  --repo "$PWD" \
  --source-sha "<exact-protected-main-SHA>" \
  --rollback-lkg "<verified-current-production-LKG-SHA>" \
  --freeze-sha256 "<fresh-readback-freeze-SHA256>" \
  --target "/srv/jason/archive/pmv4-stage-a0-sparse-<exact-SHA>.tar"
```

The command refuses non-current main, dirty/changed source, an existing output
file, any path outside the fixed evidence directory, or a production target.
`source_manifest`, `package_bytes`, and `verify_package` are pure bounded
validators; `stage_disposable` and `rollback_disposable` operate **only** in
an exact private /tmp laboratory. No method here installs production root
source. CI explicitly demonstrates root UID/GID/modes in disposable /tmp and
rollback to absence on interruption.

### Independent privileged source-staging implementation

`tools/pmv4_stage_a0_sparse_root_stage.py` implements this fixed-scope
staging action as future root-installed code. It requires fresh Entra Owner
authentication, an explicit exact-action confirmation, the existing pinned
Ed25519 signer and trust, a one-use audit claim, and the existing PMv3 lock.
It independently checks protected-main CI, immutable Git blobs, the source
scope, the freeze, the hold, the breaker and ticket runtime health.

The transaction creates only the 13 declared root-owned source files under a
private sibling directory and atomically renames it to
`/opt/jason/releases/<SHA>` without overwriting any existing release.
On failure it restores verified-owned objects to the absence baseline;
unknown or unverifiable objects make recovery fail closed.

A **separately authorized initial root trust installation** must first place
hash-pinned copies of the issuer activator, sparse source validator, sparse
root stager, and existing CI attestor, along with exact root-owned policies.
This source-only change does not install or authorize those executable controls.
The existing native root worker will independently recheck source bytes before
Stage A0 installation. **No production source tree was installed here.**

## Compartment 3 — Existing native Stage A0 installation

After Compartments 1 and 2 have separately passed their authorized production
activation and independent readback, the already-existing MCP Owner tool can
issue a **new** one-use signed exact Stage A0 request bound to the final SHA,
Stage A0 scope/manifest/freeze hashes, and 40-zero initial shadow rollback.

The existing root reconciler independently verifies root parent/target
metadata, protected main/CI, Owner proof, legacy host lock, new PMv4 host lock,
root breaker, production freeze and ticket health; it journals create-only A0
objects. Failed/interrupted operations recover ONLY exact journaled objects to
the genuine empty initial baseline. This does not enable the shadow service,
external Ticket Core, or Runbook Management.

## Separate release decisions and fail-closed gates

- This engineering authorization **does not** approve the issuer activation,
  immutable source staging, Stage A0 root installation or Ticket Core cutover.
- A future signed Owner approval for the issuer may not be reused as authority
  for sparse source staging or the A0 installation.
- CI is source-only; all root acceptance uses disposable /tmp with no provider
  keys, production images, ticket ledger or active services.
- Reconfirm fresh hashes and rollback IDs when final protected main changes.
  Never reuse the November 13 packet as a later production authorization.
- If signed approval plumbing for the sparse root-source stage cannot be
  integrated into an already installed trusted host entrypoint, **stop at the
  exact protected root activation boundary**. Do not run a mutable Git file via
  sudo, approve the 79-file bundled release, or relax JES-005/CCC/root safety.
- Source-only merge/publish decisions and production activation are distinct.

## Acceptance checklist

1. Exact source-only PR diff, owner-scope review, no merge of unrelated PRs.
2. Unit suite tests same-image behavior, unauthorized environment/mount/network
   changes, signer trust, one-use proof bindings, archive path/hash/mode/owner,
   extra files/links, interrupted staging and foreign-file refusal.
3. GitHub Stage A0 source and root-runner CI on exact PR SHA; security,
   dependency, and mandatory repository checks.
4. Disposable real-root sparse source readback and empty rollback.
5. At a later *separately approved* production gate: independent root trust
   installation of the reviewed issuer/stager, signed exact Owner action,
   same-image issuer activation with rollback readback, audited source staging,
   final signed A0 root transaction and unchanged ticket processing.

**As of source authoring:** Engineering implementation and CI pending.
**Production disposition:** NO-GO; no standing authority or production writes.
