# PMv4 Stage E — exact installed generic controller root preflight diagnostic

Date: November 18, 2026. Source-only change. NOT a production release.

The Owner's earlier exact canary command stopped after successful unprivileged
source review and sudo authentication at
PMV4_E_ROOT_DENIED:Denied:PMV4_E_INSTALLED_GENERIC_CONTROLLER_DRIFT.

The controller's independent host-read evidence confirmed on Jason at 12:44-12:46 EST:
- independent_component_release.py: root UID 0, mode 0444, regular file,
  SHA-256 1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7
- independent_component_host_adapter.py: root UID 0, mode 0444, regular file,
  SHA-256 36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce
- independent_component_release_root.py: root UID 0, mode 0444, regular file,
  SHA-256 e539e66c470469312714c2c10eb52fed293c6638a66d04049f55a4a481fe1324

All five production preflight conditions for each installed file passed
from the unprivileged filesystem read and in a Python -I isolated interpreter.
The three files' ctime and mtime were unchanged since November 17.
The observed privileged denial is therefore NOT independently explained by
controller source drift. No trusted root code, modes or controller policy
have been changed. The canary remains absent, no Owner proof exists, and
drift/breaker remain PASS/closed.

The exact canary root preflight now prints a separately calculated,
fail-closed evidence row for each of the three root files BEFORE applying
its original unchanged condition. The diagnostic row contains only the
relative preinstalled path, root UID, numeric mode, actual/expected SHA-256
and truth values for is-regular, UID=0, no symlink, no writable bits, exact
sha. If a check is false, the same preflight still denies and now identifies
the exact file; it never overwrites, bypasses, trusts the printed report as
authority, disables drift, nor issues Owner proof.

Only a newly reviewed protected-main build SHA with required CI may generate
a new immutable, unprivileged one-Owner packet. The previous packet remains
immutable and should NOT be edited, force-retried or reused after a source
change. The revised packet is still governed by the original independent
root and Owner gate. Its release action, candidate/source SHA, protected
policy SHA, OCI provenance and legacy-unit NO-GO conditions are unchanged.

Acceptance requires privileged preflight to report all three root files
verified plus the independent protected C/D/A1 receipts, healthy containers,
closed breaker, drift PASS and unchanged freeze BEFORE requesting an Owner
signature. If discrepancy persists, stop and use the printed file-specific
evidence for scoped repair; do not relax any guard or fake approval.
