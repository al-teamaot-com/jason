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
