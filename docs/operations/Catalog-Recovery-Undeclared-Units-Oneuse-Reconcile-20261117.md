# Scoped recovery-unit conflict — 17 Nov 2026

**Status:** Source-only, no production mutation until a fresh authenticated
exact-action Owner approval. This corrects a catalog-install/production-drift
conflict that prevented the already prepared financial-statement release.

## Verified incident

Four catalog recovery systemd units were installed between 15:31–15:32 EST by
a separately Owner-approved catalog controller transaction, but the frozen
production desired-state file at
`/opt/jason/current/config/production-desired-state.json`
(SHA256 `835fcb669cbc433e569797a5882d84ddf1dd206aadba56fbed180bce4ceda3e5`)
includes none of them in its allowed/required system units. The production
watchdog repeatedly produces exactly four
`undeclared_installed_system_unit` problems, opening its protected breaker.
Both installed catalog recovery oneshots report no active recovery transaction;
the root installer reports `already_installed_no_recovery_required`.
The built-in recovery command is therefore correctly **not eligible** to undo
a completed root install; do not forge an interrupted journal.

## Minimum permitted reconciliation

The source-only signed one-use
`tools/catalog_recovery_units_reconcile_root.py` requires:
- Current exact four-unit drift and open native breaker (no unrelated failures).
- Unchanged frozen revision `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`,
  freeze SHA256 `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`,
  desired-state SHA256 above, and all five protected containers running.
- Current root-owned catalog Owner approval and bootstrap trust present,
  current root-only catalog **transactions and offers empty**, all four exact
  installed systemd unit SHA256s, and no active catalog recovery service.
- Independent Entra Owner MFA and typed exact action, bound to source SHA,
  one-use manifest, rollback SHA, scope hash, and protected production freeze.
- Exclusive native release and PMv4 host-mutation locks before changing units.

After root preflight and signature verification, the installer writes a
root-owned exclusive attempt receipt and four byte-for-byte root-only backups.
It disables only these **two** optional catalog recovery timers, removes only
the **four** unit files, and runs `systemctl daemon-reload` (no production
container or protected service restart). It checks twice for **real, fresh**
production drift PASS and calls the existing native root-governed breaker
revalidation function. It verifies protected container ID/image/start-time and
frozen-file SHA invariance. If an eligible step fails, it restores precisely
the original four unit files and two enabled timers, preserves failure audit,
and leaves breaker fail-closed. It cannot be used again once attempted.

## Intentional operational tradeoff

The existing catalog root code and original signed installation evidence are
**preserved**. Catalog promotions are *not production-eligible* while their
recovery timers are absent; this is explicit and fail-closed. Catalog
deployment must later be reconciled through a separately approved native
desired-state release, not by recreating unlisted timers. The financial
component and its separately approved activation are untouched by this
reconciliation. Its existing 05:00 scheduler release command remains necessary
**only after** the native breaker is verified closed.

The recovered status must be verified via the native readback, not by editing
`production-control-state.json`, extending a waiver, stopping the watchdog,
or declaring an invented PASS.

## Acceptance

1. Protected source PR merged, required CI pass and exact source hashes pinned.
2. Unprivileged stage and signed Owner preflight PASS; isolated root host
   preflight confirms **no live catalog promotion**.
3. Exact one-use root audited action reports fresh drift PASS and native
   breaker CLOSED, all catalog unit conflicts absent, protected services and
   freeze unchanged, and rollback bytes preserved.
4. Then—and only then—execute the **separate** exact financial one-use
   Owner-approved promotion, followed by genuine 05:00 SharePoint observation.
   Do not mark the financial organizer operational until its live run is
   verified.
