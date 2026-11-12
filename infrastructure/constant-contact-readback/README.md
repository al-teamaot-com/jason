# Constant Contact independent GET-only readback

Source-only staging. No production installation or activation is authorized by
these files. The systemd **user** timer invokes one bounded reconciliation cycle
every 15 minutes. It cannot POST contacts, trigger campaigns or send messages.

The one-shot module is included in the immutable runtime image at
`jason_runtime.constant_contact_reconcile_entrypoint`. Its built-in profile
requires `JASON_CONSTANT_CONTACT_RECONCILE_PROFILE=constant-contact-aot-readback-v1`
from the deployed runtime's protected configuration. It remains disabled by
default; it cannot be enabled by importing or previewing a workbook.

The isolated systemd unit invokes `docker exec` rather than spawning another
Jason runtime service or ticket supervisor. Runtime composition uses
`maintenance_profile="auxiliary"`, so the reconciliation process does not
create a second ticket worker. The user timer has no persistent catch-up and
never runs overlapping instances of the same unit.

`install.sh` installs units disabled. **Do not run on production until the
exact candidate and rollback are approved through the native PMV3 release
transaction**, protected desired-state entries include the units, the
production circuit breaker is closed/revalidated, and live OAuth account
binding and documented consent acceptance pass. A release-gated installer must
then enable the timer and verify a real GET-only cycle and audit receipts.
Never enable from a mutable worktree or bypass the protected root controls.

Failures must not redispatch uncertain POSTs. A pending/unknown import remains
pending for GET-only retries; resolved records get terminal verified/failure
receipts. Compare ticket-worker heartbeat and scan progress before/after
activation. Roll back the scheduler independently if it impairs core service.
