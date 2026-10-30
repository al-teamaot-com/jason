# Conditional autonomous repair admission — SFC/DISM pilot

Status: **PREPRODUCTION SOURCE-ONLY — NOT EXECUTION-ENABLED**
Owner decision: issue [#2179](https://github.com/al-teamaot-com/jason/issues/2179), 2026-10-30
Provider: Datto RMM, behind Jason canonical `automation.component.execute`
Implementation: `implementation/autonomous_remediation/conditional_repair_admission.py`

## Outcome

Jason should start SFC/DISM autonomously on eligible Windows endpoints when
independently verified evidence establishes Windows servicing/system-file
corruption, then **continue other tickets** rather than holding a technician
or an active worker slot while the repair job runs. It should retain the Datto
job UID, poll status and output using authorized read capabilities, independently
verify the result, and write an internal Autotask note. Failures, ambiguity,
or a reboot-required result escalate; **never reboot automatically**.

This is a bounded repair policy, **not** a source or permission grant for
arbitrary PowerShell, and **not** a generic `standing_safe` read-only tool.

## Exact candidate and evidence

- Catalog-verified name: `Start system repair (SFC / DISM) AOT Ver 05292024`
- Catalog-verified component UID: `71463154-6eee-4f8c-a537-75b109727293`
- Provider catalog: zero variables, description says no reboot.
- Actual Datto CPT `command.bat`: **NOT YET PROVIDED or inspected**.
- Script-source SHA-256 / live version pin: **NOT VERIFIED**.
- Durable autonomy approval: **NOT ACTIVATED**.
- Provider-backed execution acceptance: **NOT PERFORMED**.
- Existing 13 approved components in #2174 / draft PR #2175 are unchanged.

Do not mistake a similarly named `Fix-DISM.ps1` in the AOT PowerShell
repository for this exact Datto package. It includes ISO download/mount and
DISM repair operations, and is NOT certified as the current provider script.

## Policy and governance gates

The new test-only admission function is deliberately provider-neutral and
**disabled by default**. A result of `ready_for_governance` allows only
proposing the exact plan to the existing governance/authorization pipeline,
not running a job or registering standing-safe authority.

1. Read and certify the current Datto CPT code and dependencies. Bind the
   approved UID, name, playbook version, and **script hash** to a verified live
   provider revision. Fail closed if changed, absent, or unverifiable.
2. Independently verify corruption evidence such as confirmed SFC integrity
   errors, confirmed DISM component-store corruption, or verified Windows
   servicing corruption. Uncorroborated user complaints or model opinion
   cannot authorize a repair.
3. Verify exact ticket→device→client binding, Windows OS, endpoint online,
   and approved/autonomous playbook policy. A lower-priority ticket/source
   cannot override a global/site/device denial.
4. Check recent *server-observed* device health: user idle, acceptable CPU
   and disk activity, sufficient free space, power source, no equivalent
   existing Datto repair job, and no previous attempt for this incident.
   Missing/stale/ambiguous safety facts **defer**, not execute.
5. Prohibit reboot, logoff, network reset, user application termination and
   disruptive service restart. An action that may noticeably affect users
   needs its own explicit approval; do not infer permission from the owner's
   authorization to perform an ordinary non-disruptive SFC/DISM repair.
6. Use the normal **Central Orchestrator** permission, idempotency, audit,
   provider API Component Level and single-dispatch gates; no direct
   provider API or shell bypass. Until a separate, verified repair-autonomy
   authorization mode is implemented, the existing generic component
   standing-safe/per-run restriction is **not** bypassed.

## Runtime continuation after admission (NOT implemented here)

Once integrated and approved:

```text
MATCHED → VERIFY_IDENTITY → VERIFY_CORRUPTION_EVIDENCE → CHECK_USER_IMPACT
       → AUTHORIZE_APPROVED_REPAIR → DISPATCH_ONCE → WAITING_JOB (release worker slot)
       → POLL_EXISTING_JOB → READ_OUTPUT → VERIFY_RESULTS
       → DOCUMENT_TICKET → COMPLETE | DEFER | ESCALATE
```

- Store `job_uid`, component identity/hash, device and ticket IDs, initiation
  evidence, execution-plan fingerprint, and idempotency key durably **before**
  reporting success.
- While Datto performs the long repair, Jason continues unrelated work; a
  targeted scheduler wake or bounded reconciliation polls job status.
- Missing output selectors or a failed read are **not** reasons to dispatch a
  second job. Re-poll only the previously recorded job.
- Distinguish SFC/DISM success, corruption still present, source errors,
  pending reboot, access denied, timeout, and provider transport failures.
  Never close a ticket solely because job submission succeeded.
- Cap one repair per incident plus site/global concurrency and I/O budgets.
  Escalate or defer if conditions no longer meet the non-disruptive contract.
- Evidence and internal notes must redact sensitive paths, users and secrets.

## Source validation performed

The current source-only prototype has deterministic fixtures and adversarial
tests for unsupported/model-only triggers, wrong tenant/device/UID/name,
stale or mismatched script hash, missing durable approval, reboot requests,
repeat attempts, missing or stale telemetry, busy users/CPU/disk, low storage,
offline endpoint, battery power, duplicate job, missing resource thresholds,
and invalid floating-point measurements.

**Tests are simulation only.** They do not establish the actual CPT's
reboot behavior, demonstrate provider acceptance, or prove end-to-end ticket
continuation. The candidate remains **0% operationally deployed** until the
real Datto source, approval mode, runtime integration, provider-backed pilot,
production release and readback have all succeeded.

## Review and release boundary

The owner approved the *conditional autonomous outcome*, not an unreviewed
deployment or an exemption from the no-disruption rule. The previous
unmerged per-run-only development branch was retired because it encoded the
wrong goal. This new isolated worktree branches from protected
`main` at `b9ded6e242183a18f3299e05e5b517a0d8375ad9`.

The #2175 component-execution work may overlap when a future repair-autonomy
mode is integrated. Reconcile against current protected main, review active
implementation-sensitive PRs, run relevant CI/acceptance, verify production
health and last-known-good rollback SHA, and seek exact-SHA final deployment
authorization. No release freeze is lifted by these source/tests.
