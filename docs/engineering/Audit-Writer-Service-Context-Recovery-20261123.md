# Audit worker service context and pre-cutover recovery

Status: source engineering and isolated tests. The production adoption of `f0f71c46e054f46f6cba1f945a404f148f441501` failed before a database barrier, producer replacement or initial data claim. No corrected source is deployed by this document or a source merge.

## Verified failure

The Owner's Root preflight, independent Entra identity check and exact action approval passed with scope `6b792b74869d31f2072929d8ace08236161284b5875d3c2fb7a9dff6d3c56c80`. The installed worker and its one automatic recovery attempt failed launching the UID1000 SQLite helper. The journal reports required PAM session/resource-limit errors inside the hardened systemd service. The same installed helper succeeds as UID1000 outside that login-session handoff. The previous fixture exercised Root storage operations but did not reproduce that service/session boundary; component test success was insufficient release evidence.

The live original canonical inode remained unchanged, its maintenance trigger/schema inventory was empty, the catalog remained legacy generation zero, and the six protected peer identities were unchanged. The native watchdog subsequently opened the breaker for the failed new release service and the inactive newly required maintenance timer. Fast health and the already completed genuine full integrity/authority restore proof remained valid. A read-only check also confirmed zero current-generation consumed claims at the next drain gate.

## Execution repair

The fixed background helper now uses the existing Root process's explicit UID/GID1000 transition, an empty supplementary group set and a fixed minimal environment. SQLite helpers and native revalidation callers share that identity contract. The Python isolated interpreter, fixed installed entrypoint, finite SQL operations, process-group timeout cleanup, `NoNewPrivileges`, capability bounds and all unit hardening remain in place. No `CAP_SYS_RESOURCE`, Docker-group access, PAM override or general privileged shell is added to production. The real worker first probes its writer-account execution using a read-only state query before touching the database barrier.

The isolated test uses the restricted capabilities, NNP and bounded nofile limit with a required failing PAM session policy in a private container tmpfs. It verifies that the old login handoff is denied while the fixed helper runs as UID/GID1000 with zero effective capabilities and no supplementary groups, performs actual SQLite reads and creates/removes the maintenance barrier. Host PAM is never changed by the test.

## Installation versus readiness

The inactive timer is declared allowed during initialization, rather than falsely required before its activation. The final exact desired policy is stored privately and hash-bound to the Owner scope. Only a successful real scheduled maintenance cycle plus an active, enabled timer permits promotion to the required policy. Native drift and guarded revalidation run after that final policy change. This changes neither the 27-slot ceiling nor the six fixed recovery slots; an initialization policy is not operational acceptance.

## Exact recovery of this known failed adoption

The existing installer exposes `--repair-before-cutover` for this fixed failed candidate/scope only. It requires exact Main CI, original immutable Owner/producer records, Root source/unit/policy hashes, genuine fresh native health, exactly the two known installation drift findings, the unchanged canonical identity and producer configurations, legacy generation zero, no barrier or journal metadata, no initial claim and no migration/archival work. The persistent Root maintenance lock is preserved and used. Unknown data, another cutover, a different failure, unrelated drift or changed target bytes denies the repair.

The repair obtains one fresh independently verified exact-action Owner decision for the corrected source and remaining migration. The prior immutable bootstrap/approval is retained. Its failed private execution records and exact before-images are preserved in a separate Root-only ledger under `/var/lib/jason-owner-release/audit-journal-service-context-repairs/<candidate>`. The old consumed grant is not replayed and no old failure is mislabeled as accepted or rolled back. The new execution claim explicitly references its predecessor and is governed by the new Owner scope.

Under the existing production/host locks, the failed release's boot path is disabled while exact Root source, profile and adoption/plan before-images are replaced transactionally. The original producer specifications, canonical data and archive custody are preserved. Before enabling the repaired release, the installer runs genuine native fast health, drift and the existing independent Root transition to close the breaker. It never edits breaker state or merely ignores the failure. Only then is the durable new claim queued. The remaining cutover, full archive integrity/content parity, legacy reconstruction/cold restore, safe local reclamation, real timer cycle and actual consumer reads remain required.

A power loss or response loss has a bounded, frozen-source `--resume-context-repair` route, one retry and an eight-hour execution window. Known before/after bytes may resume; unknown bytes, a changed dataset/catalog/peer, unverified Root custody, an expired grant or another retry deny. Before queueing, transaction rollback restores the original bytes and modes while preserving both decisions and execution evidence. Once queueing is possible, filesystem undo is prohibited; the existing event-preserving release recovery owns subsequent work.
