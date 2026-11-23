# Audit journal writer handoff: Root cause and bounded correction

Verified at 2026-11-23 19:09 UTC after previously exact-approved 20b325484 release worker failed twice with PermissionError errno 1 at phase verifying_writer_account_execution.

## Reproduction

On an isolated GitHub-hosted Ubuntu 24.04 machine (no production mounts, credentials, provider access, or persistent unit mutation), an ephemeral systemd-run --wait --collect unit used precisely the production service User=root, Group=root, NoNewPrivileges=yes, CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER CAP_SETUID CAP_SETGID CAP_SYS_ADMIN CAP_SYS_PTRACE CAP_KILL CAP_AUDIT_WRITE, RestrictAddressFamilies=AF_UNIX AF_NETLINK, TasksMax=32. A disposable Python test used subprocess.run with fixed user=1000, group=1000, extra_groups=(), start_new_session=True.

Without ambient capabilities: CapBnd 00000000202800eb; CapEff 000000002028006b (missing only CAP_SETUID), NoNewPrivs=1. Plain, start_new_session, extra_groups and group=1000 passed; user=1000 and full writer UID transition failed PermissionError errno 1.

With only AmbientCapabilities=CAP_SETUID: CapEff 00000000202800eb, CapAmb 0000000000000080, NoNewPrivs=1. All trials including fixed UID1000/group1000/no-supplementary-groups/full handoff passed. The original disposable Docker fixture explicitly granted CAP_SETUID and was a false negative for this host systemd constraint.

Evidence: GitHub Actions disposable workflow runs 45245665021 (with SETUID and SETGID ambient) and 45245957596 (with only CAP_SETUID), source-only branch fix/audit-journal-uid-handoff-20261123.

## Security-preserving fix

Add only AmbientCapabilities=CAP_SETUID to three Root-owned journal services: release, maintenance and data recovery. Preserve NoNewPrivileges=true, existing bounding limits, exact writer UID=1000, UID/GID no supplementary groups, no additional address families, no service or provider restarts. Do not add CAP_SYS_RESOURCE, CAP_SYS_ADMIN ambient or CAP_SETGID ambient.

The disposable CI workflow is diagnostic only and must NOT be merged into protected Main. Required protected verification includes exact profile tests, native writer/rollback suites, ROOT-only audit evidence and genuine runtime readback in target host before accepting the patch.

## Production state and recovery limits

Owner approved exact candidate 20b32548402d160f9c6a5ee33a0a17592eb9fa68, scope 6d815c67f58ec9fa5eb3e2367259a53d53baf30daaa460d45b4720019291d7e8; the Root installer queued its release. The release reached writer identity, failed and exhausted systemd's two automatic attempts. Live catalog remained legacy generation 0, archive segments empty, and root disk still 98% full.

An already queued/recovering immutable Owner grant is not fresh authorization to change its reviewed unit properties. Deployment of the three production unit changes must pass independent exact-source/scope/rollback approval and Root governance; do not modify prior ledger, silently set environmental overrides, reset breaker, or restart/re-execute failed releases under unreviewed context.

After a controlled recovery, full migration objective is only complete once history parity, archive readback and cold restore, current live writes, scheduled rollover and actually reclaimed root blocks are verified.
