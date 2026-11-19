# Scoped-backport four-unit inventory reconciliation

## Verified live incident

The independently installed scoped-backport controller has four systemd units which exactly match source at commit `6adc19744fc7464ef3ba34d1ce0b3b20e9e69684`. The installed root worker matches the pinned public attestation. The production watchdog reports only these four as undeclared installed services. Its circuit breaker is open.

## Prepared correction

This source changes only the four names in the allowed system unit inventory. The read-only evidence module checks the unit SHA-256 hashes, trusted root-install attestation, and the exact live drift set. The one-use root transaction module requires an independently signed Owner approval binding the source, baseline and candidate protected-policy hashes, unit hashes, rollback, freeze, scope and manifest. It also checks that the existing protected root policy and immutable source are unchanged. Its intended effect is to admit exactly those four units, run the existing watchdog, and roll back the old policy if verification fails. It does not close the circuit breaker, lift the freeze, replace containers, or activate providers.

The protected production inventory is not readable by this session; local remote-command policy also prohibits sudo. Therefore, root-policy baseline verification and the required signed one-use approval have not been performed. Source evidence and ChatGPT instructions are not substitutes for those controls. No root production change has been made.
