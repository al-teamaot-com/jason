# PMv4 Stage C: final drift after real scans

**Source-only as of November 18, 2026.** No production action or Owner proof
is issued by this change.

The Owner-authorized Stage C handoff source
ea7c65a4e92b2c2251c6cf965b3cca56a355c2a1 successfully activated
jason-pmv4-ticket-core and a healthy external runtime, then returned
C_RESUME_POSTFLIGHT_DRIFT_DENIED before waiting for its required two
ticket scans. The protected root rollback restored embedded mode;
MCP remained running; the existing canonical SQLite data did not move.
The native drift watchdog subsequently reported PASS with zero problems,
and the protected breaker remained CLOSED.

Read-only simulation shows that the approved candidate policy reports PASS
with the external worker and exactly one additional stopped rollback
container. There is no captured structured reason from the failed in-flight
drift check, so an unobserved transient condition is a *hypothesis*, not a
verified root cause. We must not repeat a production cutover blindly.

## Minimal postflight ordering correction

The isolated root code now performs, in order:

1. Verify healthy runtime, MCP identity and exact external worker manifest
2. Wait for **two real ticket scans**, using the original ledger baseline
3. Require **native drift guard PASS** under the exact root-owned candidate
   policy. On failure, print bounded, redacted structural drift reasons
   and roll back
4. Require native production drift watchdog PASS and unchanged freeze/hold
5. Independently require the protected root release state and breaker PASS
6. Write the exact one-use acceptance receipt only after all of the above

This removes only a *redundant early* drift abort before worker stabilization.
It does **not** disable the watchdog, grant a blanket exception, mask any unit,
change the approved drift policy, force-close the breaker, or authorize later
PMv4 stages. Any final unexpected drift forces rollback to the already proven
embedded worker. One new exact authenticated Owner authorization is required
because the prior one-use release approval was consumed.

The test coverage exercises success ordering, negative unknown-container
drift, withheld acceptance receipt, redacted failure diagnostics and
rollback on native watchdog failure.

## November 18 follow-up: use reviewed candidate bytes for the redundant read-only probe

The Owner-approved cutover on source e9c64032d2ab984d559fb90cc756e9f653762a4c
successfully started the separate worker and completed two genuine ticket scans,
both with zero duplicates. Its additional standalone drift command returned
code 1 and no JSON result (PMV4_C_FINAL_DRIFT_PROBE_FAILED=1), so the root
transaction correctly rolled back to healthy embedded-worker mode.

The standalone command had used the root-only
/etc/jason/release-readback-recovery/production-desired-state.json path.
The same command returns a Python PermissionError against that path under the
unprivileged host account; this matches the observed code 1 but is not
independent proof of the exact exception in the root context because the
postflight did not expose stderr. Executing the existing production guard
read-only against the SHA-pinned and reviewed watchdog-candidate.json returns
PASS with zero problems.

The minimally corrected postflight rechecks BOTH the candidate SHA-256 bound
into the exact Owner-approved plan AND byte-for-byte equality with the
installed root-owned production policy before running the standalone read-only
guard against those candidate bytes. The regular native root drift watchdog,
the protected breaker and readback gate, two real scans, freeze, immutable
release source and rollback remain unchanged and mandatory. Missing, tampered
or mismatched policies fail closed and roll back.

Previous Owner proof is consumed and cannot authorize this changed release.
No production mutation is made by this source correction.

## November 18, 06:44 EST: root child-executable search path

The next Owner-approved source 85aec2fce36014dd2c4668fd83789f831e262ab9
passed two genuine ticket scans and SHA-bound policy validation, but the
standalone root drift Python process exited 1 with a FileNotFoundError.
The protected root cutover correctly rolled back and production was verified
healthy in embedded mode (breaker CLOSED, native drift PASS).

The existing native guard executes bare `runuser` for its user-systemd
inventory when effective UID is root. On this host `runuser` is at
`/usr/sbin/runuser`. A restricted child PATH without `/usr/sbin`
reproduces the exact FileNotFoundError; a trusted PATH containing
`/usr/sbin:/usr/bin:/bin` resolves the required native commands.
The exact root process's PATH was not independently captured, so this is
a high-confidence diagnosis with a direct reproduction, not a new drift waiver.

The minimal correction passes `PATH=/usr/sbin:/usr/bin:/bin` **only** to
the existing final read-only drift guard and native drift watchdog subprocesses
after two actual scans. Approved policy bytes, freeze, breaker, native watchdog,
signature checks, result statuses, one-use approval and rollback are unchanged.
Tested success and failures; no production changes in this source PR.
