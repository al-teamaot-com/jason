# Jason governed Linux shell — development-worker pilot

**Status:** Proposed capability; **not production-activated** until exact-SHA release validation and configuration.
**Owner:** Jason Architecture Authority / AOT Owner
**Tracking:** GitHub #1459
**Scope:** One owner-designated, enrolled development-worker endpoint (currently Claw2-PC), not arbitrary Datto clients, not production Claw.

## Boundary and purpose

Jason reuses `automation.component.execute` and the existing Datto RMM quick-job execution identity, rather than creating a second remote-command system. The exact provider component must resolve in the complete live Datto catalog to:

- UID: `bc7c4531-6869-4658-b1d6-7639a477045e`
- Name: `Run Ad Hoc Command (Shell) [MAC] [LIN]`
- Reviewed input variable: exactly `usrInput`, string, present, <=20,000 characters.

This component uses shell evaluation, so **no shell input is classified as standing-safe**. The exact component is forced `per_run` even if configuration or a durable component approval suggests otherwise. Unknown variable names, omitted command, unreviewed or renamed component identity, missing worker enrollment, or a different endpoint fail closed.

## Enrollment configuration

The server-operator-managed setting `JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID` MUST contain one exact provider UID in **both** the MCP canonicalization environment and the actual execution runtime. Missing or mismatched setting denies the shell. The value may not be supplied by a tool caller, chat model, worker, or task payload.

For the first pilot, after independently confirming the machine role and validating owner approval, the target is `Claw2-PC`, Datto UID `13eda165-08e0-ec79-026a-985b37e2eb9e`. The live production OpenClaw host `aoteq-OptiPlex-3040` is explicitly excluded.

The normal `JASON_DATTO_COMPONENT_EXECUTION_*` configured allowlist/profile, exact principal grants, identity-bound approval, bounded credential, Central Orchestrator, provider readback, execution-plan binding, audit and output-read workflow remain mandatory. Enable the exact live shell component in the server-side configured catalog with approval mode `per_run` if not already covered by the governed live-catalog per-run fallback.

## Release and usage

1. Confirm no current production or unknown service role on the target; verify authenticated device identity and observed health.
2. Merge only a source revision reconciled with current protected `main`, validated by required checks and reviewed for active code overlap. Promote only under Jason's existing serialized Release Manager, with rollback and independent live identity verification.
3. Configure the exact worker UID through the approved host configuration management; do not inject credentials or command text into unrelated provider environment.
4. Authorize each actual command invocation under the exact AOT Owner approval on the exact host, and carry `explicit_approval=true` through the established MCP action. This owner designation does **not** grant autonomous workers the right to set that flag or execute unrestricted shell unattended.
5. Execute only a harmless initial `uname -srm` or similar diagnostic; retain its Datto job UID, poll that same job to completion, and read stdout with the exact returned job/device/component selector tuple. Never redispatch because of incomplete output retrieval.
6. After proving the transport and inspecting installed services/disks/OS, design an idempotent desired-state worker bootstrap with controlled, documented maintenance/reboot and audit. No production secrets, alternative release manager, or direct provider access on a worker.

## Acceptance and failure behavior

- Test exact UID/name `usrInput` pass; reject unknown variables, missing input, UID collision and renamed component.
- Test that `standing_safe` config is forcibly reduced to `per_run`, that absent technician approval stops before orchestrator, and that approving one run allows only that run.
- Test that missing enrollment or another managed Datto device fails in MCP and at the runtime execution-plan boundary, before any provider write.
- Test that the existing Windows ad-hoc PowerShell command policy and other Datto components retain their existing semantics.
- Failures must preserve correlation and audited reason, report zero provider attempt where applicable, and never retry via more privileged direct credentials.
- Worker readiness is not achieved until safe provisioning, desired-state verification, recovery and task checkpointing are proved independently. This change enables a governed diagnostic transport only; it does not itself provision the worker.

## Related authority

- `docs/foundation/J-002-Constitution.md`
- `docs/engineering/Jason-Change-Integration-and-Release-Standard.md`
- `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`
- GitHub #1459
