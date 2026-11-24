# Exact Jason DRMM root identity probe — source-only candidate

Date: 2026-11-24. Requested by the AOT Project Owner in ChatGPT: extend the governed per-run DRMM shell path to the exact **Jason** host for a read-only root identity check. The audit database migration is a different, separately governed release.

## Observed target

- Hostname: Jason; Datto RMM site: Atlantic Office Machines
- Exact Datto device UID: `85fc3097-ac2f-18b2-afc4-6cf07131275d`
- Provider-reported device class: Desktop; OS: Ubuntu Linux 24.04
- Linux Datto RMM `AEMAgent` observed running as root
- Exact live Datto component: `bc7c4531-6869-4658-b1d6-7639a477045e`, "Run Ad Hoc Command (Shell) [MAC] [LIN]"

## Security boundary

This is **not** the Claw2-PC development worker enrollment. Production Jason is not a development worker. The component is ALWAYS per-run; it cannot be promoted to standing-safe by configuration. Both MCP and provider code enforce the exact device UID, component UID/name, `device_class=Desktop`, an exact read-only `usrInput=id -u`, and no additional variables. A changed command, missing/mismatched gate, other endpoint, changed component, autonomous per-run selection, expired/invalid approval, or provider disagreement fails before a Datto POST. A changed or revoked activation gate between preparation and execution also denies POST.

The activation variable `JASON_DATTO_JASON_ROOT_PROBE_DEVICE_UID` is **empty by default** in both MCP and runtime deployment scripts, and accepts only the exact pinned UID. Code deployment or PR merge alone does not activate any root path. Existing production freeze, breaker, Owner identity verification, release approval, rollback and audit controls remain authoritative. No database writes, service restarts or reboot are authorized through this diagnostic.

## Bounded deployment and acceptance

1. Independently verify the Owner's Microsoft Entra identity and record the exact candidate SHA, the two changed service images/revisions, rollback revision/images, activation variable/UID, `id -u` command, scope hash, and proof of current production freeze state. Approval may come from the Owner's authenticated ChatGPT session if the existing Jason issuer verifies and records it.
2. Require review, tests and production release gates. Only the governed release manager may publish the reviewed MCP/runtime revisions and set the exact gate in **both** services. Preserve untouched services, production Core and existing Claw2 enrollment. No in-place edits of running containers.
3. Verify provider target UID/site and current online evidence, then call the governed `automation.component.execute` with the exact Datto component, `variables: {"usrInput":"id -u"}`, target UID, and a direct authenticated per-run instruction. Record correlation and returned job UID.
4. Poll **the same job** with `automation.job.read`; after terminal status read `automation.job.output.read` using Jason's returned selectors. Never redispatch an ambiguous job. Confirm stdout contains only UID `0` (allow standard DRMM output framing), exit code 0, and check release audit evidence. Verify no nonapproved provider/host mutations occurred.
5. If any gate fails, stop and recover only the scoped MCP/runtime changes through the approved rollback. Do not weaken the freeze, replay an expired release, or touch the database. No root command executed = no root verification.

## Engineering evidence

- Isolated local 17 focused MCP/provider/profile tests passed on 2026-11-24 (no production mounts, provider writes or root operation).
- Broader MCP tests require an authenticated Datto catalog read in their existing fixture; an identical baseline test on an unchanged prior branch fails with `MCP_AUTHENTICATION_REQUIRED`. This is not proof of a new regression. CI should run the reviewed validation suite independently.
- Source-only candidate until governed release/activation and live DRMM job readback. This document does not authorize deployment.

## Test-ledger isolation finding

During the first host-only harness runs, the unconfigured default path `/var/lib/jason/openclaw/governed-execution.sqlite3` was created. Read-only inspection on 2026-11-24 identified exactly two `automation.component.execute` **reserved** rows with five-minute expiries, and no consumed/provider-executed rows. Preserve those historical test records; do not delete or treat them as an Owner approval. No live Datto dispatch was made. The root probe tests and CI now pin approval storage to a separate disposable test ledger, preventing further host default-path writes.
