# Audit health: preserve the frozen journal while repairing native readers

Status: source engineering only. No production installation or new Owner grant.

## Verified problem and rejected predecessor

The accepted audit forward migration retains 34,616,410 historical events,
reports a first scheduled rollover, and has an active maintenance timer.
The frequent native health service fails opening WAL-mode SQLite beneath
ProtectSystem=strict when WAL/SHM sidecars are absent. Current independent
production drift reports that service failure and leaves the breaker OPEN.

PR #2736 correctly investigated private copies, but its proposed journal_health.py
replacement is **not an installable production scope**: the installed
root_controller verifies every trusted source against the original Root policy,
and the original immutable adoption receipt binds that policy. A two-file swap
would break ordinary maintenance with JOURNAL_TRUSTED_SOURCE_CHANGED.
Do not deploy that packet or rewrite its old approval/policy/adoption evidence.
Its earlier synthetic sandbox result does not accept this new repair.

## Corrected change

Keep the whole implementation/orchestrator tree and all frozen tools unchanged.
Add one private health adapter alongside the three existing native readers.
Reuse the frozen catalog/coverage validators, profile, exclusive handoff lock,
SQL proof routines and existing scratch directories. Native frequent schema
reads, full integrity, restore comparison and both evidence validators use only
the private copy. No SQLite connection opens the canonical live audit file.
The reader rejects unexpected custody, symlinks, torn source identity, ceilings,
invalid coverage, overdue outcomes and copy-budget exhaustion. Copying holds
the existing writer gate exclusively; a five-second checked budget bounds
ordinary copy progress. Filesystem calls can still incur kernel I/O latency.

Production native targets, all root:root 0444:

| Source | Native-health target | Effect |
| --- | --- | --- |
| tools/audit_journal_health_private_reader.py | audit_journal_health_private_reader.py | Add |
| tools/audit_journal_fast_health.py | openclaw_authority_fast_health.py | Replace |
| tools/audit_journal_operational_health.py | openclaw_authority_operational_health.py | Replace |
| tools/audit_journal_full_health_snapshot.py | openclaw_authority_live_audit_full_snapshot.py | Replace |

Target directory: /usr/local/lib/jason/audit-journal/native-health.
No general fast-health implementation is replaced. The pinned journal sources,
original audit policy, adoption receipt, recovery grant, systemd directives,
container images and service identities remain unchanged.

## Governed execution and rollback

Extend the existing tools/audit_journal_install.py staging, protected-main CI,
Root locks and independently licensed Entra Owner verifier. Do not add a new
scheduler, signer, approval store, root service or standing authority.

Action: REPAIR-EXACT-AUDIT-HEALTH-NATIVE-PRIVATE-READER.

The read-only Root preflight verifies the original adoption and every actual
trusted-source pin, all native protection digests, exact three before-images,
absence of the new helper, accepted audit/rollover, protected container identities,
idle health/release workers, active health timers and every effective systemd
unit configuration hash. It permits only the documented frequent-health failure;
unknown or additional drift fails closed. Root scope and source SHA must be
reviewed before an exact production decision. Neither merge nor preflight is
production consent.

The new exact Owner decision is separate from old consumed grants. After that
one decision, revalidate under the existing native locks, record immutable
approval outside filesystem rollback, briefly pause the two health timers,
require both health services quiescent, atomically add the helper and replace
only the three native readers. Restart the same timers. No daemon reload or
application/container stop is required.

Acceptance runs a fresh full proof, frequent proof and the existing adopted
maintenance service, requires three distinct fresh native drift PASS observations,
and requests the existing native revalidation to close the breaker. Compare
all four installed digests, every frozen source/policy/adoption, effective unit
configuration and protected peer identity after the operation. The full scan
has a 5,500-second bound. These checks are required live, not inferred from CI.

On any failure, stop only the two health services/timers as needed for safe
rollback, restore all three exact original files through the existing durable
transaction, remove only the newly added helper, verify custody and source
hashes, and restore the prior timer state. Preserve approval and failure records.
The prior health defect may return; do not label rollback as healthy recovery.
A crash or unknown transaction outcome fails closed for Root reconciliation;
never replay an old approval or erase its receipt.

No direct audit database changes, historical deletion, provider writes,
container restart, freeze change, policy rewrite or direct breaker reset.
The acceptance maintenance invocation uses only its existing adopted policy.

## Verification

- 649 journal/native/installer/read regression tests passed in the source tree.
- Seven exact-scope/Owner-denial/state-change preflight checks passed after
  adding effective unit hashes and Root directory custody.
- Core journal tree and frozen maintenance/control source have zero diff
  against protected main 33ea8e547102ab406bd5d7506a0fbe306d258b04.
- Hosted CI additionally exercises a genuine Root-managed strict systemd mount
  over synthetic data and real UID0 rollback after each of four publications.
  Those checks must independently pass at the actual source SHA.
- Live native Root preflight, Owner approval, installation, recurring health and
  end-to-end production acceptance: pending.

Release class: High-Risk (native production health/release infrastructure).
All unrelated production and dependent feature activation remain held.
