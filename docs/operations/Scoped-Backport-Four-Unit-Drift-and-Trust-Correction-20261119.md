# AOT / Jason — scoped-backport root-control corrective release

**Lifecycle:** Source-only engineering; not a production root policy change,
service restart or approval. The *previous* installer completed on 2026-11-19
with one authenticated Owner installation approval. Its changes were exact and
audited, but the installed four units were not declared in the independent
root-owned production desired-state configuration.

## Verified failure and impact

The original root installation attestation passed:
- Installed production-safe root controls pinned to protected main
  `6adc19744fc7464ef3ba34d1ce0b3b20e9e69684`.
- Enabled the dedicated recovery timer and typed-request listener.
- Preserved `jason-runtime`, `jason-mcp-pilot`, PMv4 Ticket Core/Shadow Gateway,
  OpenBao, original production freeze and provider identities.
- Native stage request
  `3f2f6b84df9a47d2a1fb9d1bf7ca35d4` was consumed, but **denied**
  before production eligibility. The initial stage-denial reason was not
  recorded because the installed worker recorded only a generic exception
  class.
- A subsequent, independently root-evaluated production drift identified
  **exactly** the following four `undeclared_installed_system_unit` findings:

```text
jason-scoped-backport-recovery.service
jason-scoped-backport-recovery.timer
jason-scoped-backport-requests.path
jason-scoped-backport-requests.service
```

The production drift watchdog correctly opened the breaker. This was a
configuration omission in the release-control installation, **not**
authorization to disable the watchdog, ignore the breaker, replace production
containers, or create an Entra group.

## Additional engineering defect

The original pinned source admission required current GitHub protected main
to remain at the install commit. Unrelated protected-main merges make that
condition untrue even when the exact reviewed M365 and root code is unchanged.
The root worker was also not emitting a bounded root denial code.

The corrective source changes:

1. Permit a newer protected-main commit **only** when the installed/pinned
   SHA is its ancestor and every named immutable release-control, systemd
   unit, release manifest and Microsoft group source file remains
   byte-identical to the reviewed pinned SHA. Unfetched history, rewritten
   branches, changed source, altered manifest or unrelated Owner/pilot code
   fails closed. **No production main-only release check is disabled.**
2. Emit only constant-coded, bounded `SCOPED_BACKPORT_*` denials from the
   root worker, never token-bearing provider errors or arbitrary stderr.
3. Use one identical root-private and operator-readable eligibility record
   so timestamp differences cannot accidentally make an otherwise approved
   release ineligible.
4. Preserve existing one-use cryptographic Owner proof, immutable image IDs,
   exact rollback, breaker/production lock and per-Graph-change approval
   boundaries.

## One exact root maintenance transaction

The future reviewed `tools/scoped_backport_four_unit_drift_reconcile.py`
performs a single separately scoped authenticated local `al` sudo +
fresh Entra Owner action. It computes its own exact root policy before/after
digests under root, verifies the installed unit SHA256s against the prior
trusted installation policy, verifies an original LKG baseline and freeze,
requires **only** the four expected drift names, and pins its own source
to a clean current protected-main commit byte-identical to a CI-green
reviewed SHA.

The exact approved writes are:
- Add those four names to `allowed_system_units` of
  `/etc/jason/release-readback-recovery/production-desired-state.json`.
  Do **not** add them to required units or modify other JSON fields.
- Replace only the installed trusted root modules
  `tools/scoped_backport_release.py` and
  `tools/scoped_backport_native_root.py` by their byte-reviewed,
  root-owned read-only source.
- Update only those two hash fields and the trusted source/CI SHAs in
  the existing root-private install policy and its nonsecret, root-owned
  public attestation.
- Pause/resume only the newly installed scoped request path and
  recovery timer, under the existing production transaction lock.
- Run the existing production-drift-watchdog one-shot, require a root
  `PASS` with no problems, validate native root handler attestation,
  and verify original production container IDs and freeze are unchanged.
- On *any* failure, restore the exact prior root-owned bytes and listeners,
  or fail closed with an explicit incomplete recovery status.

The owner proof is recorded durably before any write, bound to action,
source, before/after policy hashes, two exact code-file digests, unit names,
rollback SHA, freeze/hold digests and one-use scope SHA256. This grants
**no** standing authority, Graph POST, runtime/MCP restart, production
unfreeze or native release approval. The existing root production
transition remains responsible for independently revalidating and closing
the breaker after a clean watchdog result. Manual breaker closure is
strictly prohibited.

A nonmutating root-stage probe also checks the existing staged images,
credential mount metadata and reviewed source without bypassing the
breaker or creating a release record. That diagnostic reports only a
bounded code to avoid repeating an opaque failure.

## Release and acceptance sequence

1. Review tests, CI/security scans, source diff and exact-scope packet;
   merge the source-only fix through protected main, preserving the
   freeze and all running services.
2. Refresh source SHA, reviewed CI SHA, signed exact installation
   scope and frozen production checks. Do not reuse an old digest.
3. Use **one** authenticated local Owner authorization for the *exact
   corrective transaction* described above. The prior bootstrap's
   one-time installation approval does not authorize a different root
   policy write, and an authenticated ChatGPT session alone cannot
   manufacture a root-protected signer proof.
4. Verify root policy, self-attestation, watchdog `PASS`, and unchanged
   containers/freeze. Independently revalidate the breaker through
   the existing root transition mechanism; never force-close it.
5. Only then retry native `scoped-backport-stage`; verify exact
   eligibility and single root/public receipt. Obtain a separate
   signed one-use exact production release proof only when eligible.
6. Do not authorize any Microsoft Graph group creation or membership
   mutation from this maintenance correction.

**Current production state at engineering start:** Four undeclared unit
findings, breaker open, no Entra native eligibility, no Graph provider
changes, existing Ticket Core/runtime/MCP running. This document does
not claim a corrective deployment or production closure.
