# Stage E exact root policy baseline after scoped backport maintenance

Status: source-only correction, November 20, 2026. No Stage E cutover claimed.

The Owner supplied a sudo readback of the root-only desired-state file. Its
exact SHA256 is a4358f564c7b5c6ede6ccfa32d884760a247a2d5672440dbc80d771893868608.
The prior Stage E baseline was
4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953.

Reconstructing the supplied bytes from the previous Stage D policy and adding
exactly four allowed system units reproduces the supplied SHA256. Removing
those four additions reproduces the previous exact SHA256. No required unit,
container allowance, rollback capacity, forbidden execution prefix or other
field differs.

The four preserved entries are:
- jason-scoped-backport-recovery.service
- jason-scoped-backport-recovery.timer
- jason-scoped-backport-requests.path
- jason-scoped-backport-requests.service

The separate maintenance is described in
Scoped-Backport-Four-Unit-Drift-and-Trust-Correction-20261119.md. The observed
root-owned public attestation reports trusted source
24651789b5fc8ee79d46b54151ac36280e83efad and reviewed CI
0baeb8155758b04537bdca425b4578d13324efb0. Stage E does not grant new authority
to those controls or overwrite their policy.

## Exact correction

The future Stage E manifest, root current-policy readback and replacement
admission marker require the one exact new policy hash. Arbitrary root-policy
changes still fail closed. The native code transaction derives only the
reviewed six-trigger delta from those exact current root bytes, preserving the
four scoped-backport entries and every unrelated field.

The original generic canary receipt remains pinned to its historical
4c9db0f4... policy. Its live cleanup probe independently requires the new
reviewed production baseline. Neither the canary receipt nor its signature,
approval identity, manifest, freeze pin or transaction time is rewritten.

The installer previously ran its pre-approval probe from the older installed
bootstrap source. That old source cannot validate a newer reviewed baseline.
The isolated mode now verifies all archive bytes against protected Git and CI,
then executes only the read-only probe from an immutable copy in a root-private
volatile directory. This copy is removed on success and denial. Installed
bootstrap trust, root policy and services are unchanged by the probe.
Permanent installation and native execution remain behind exact Owner
authorization and the existing independent native gates.

## Required verification

A fixture retains the exact supplied policy bytes. Regression tests verify
both historical/current hashes, preservation of the four entries through
native apply and byte-exact rollback, historical canary signature context,
current cleanup checks, and volatile root preflight cleanup on success/failure.
Disposable UID0 CI verifies root ownership and modes.

After protected review/merge, rebuild the immutable package and verify every
file against exact Git objects. The local root launcher must independently
check the live new hash and all other prerequisites before asking for its
one exact Owner decision. Production readiness requires actual native
acceptance and independent post-cutover operational verification.
