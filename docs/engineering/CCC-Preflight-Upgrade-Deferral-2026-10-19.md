# CCC checker-currentness: safe automatic-promotion deferral

## Confirmed production incident

On October 19, 2026, owner-approved production-control-core release
ae39bc1d579bf6a07aca031a3a97f317f60a169c remained production_eligible
with preproduction and rollback readiness verified. The root-installed
CCC checker remained at revision 5277d29318c5ce31160ccb56055a8f83eb7bf4a9.
Forced CCC preflight correctly reported checker-currentness NOT_PROVEN and
runtime-source-alignment NOT_PROVEN. The latter is permitted only as the
expected pre-mutation runtime transition; the former blocks deployment.

The scheduled auto-promoter retried the approved release every five minutes,
raised ReleaseManagerError from pre-mutation CCC, and left the systemd user
release-manager service failed. Production drift monitoring reported the failed
user unit and reopened the root-protected circuit breaker, even though the
installed runtime and MCP remained on verified LKG e6503eab.

## Narrow fail-closed correction

The independent CCC report remains authoritative. The controller validates
schema, candidate and runtime SHAs, trigger, unique mandatory checks and
overall result, then distinguishes precisely two pre-mutation patterns:

- Checker currentness NOT_PROVEN alone.
- Checker currentness NOT_PROVEN together with expected, and only expected,
  runtime-source-alignment NOT_PROVEN.

Only those two patterns, with overall report NOT_PROVEN, become a dedicated
CCCCheckerUpgradeRequired error. All other pre- and post-mutation
NOT_PROVEN/FAIL results, owner approval gaps, missing checks, changed identities,
malformed reports and failing infrastructure checks remain hard failures.

The scheduled *promote-eligible* path catches this typed prerequisite and
returns normal idle status with a structured
RELEASE_MANAGER_AUTO_DEFERRED=ccc_checker_upgrade_required indicator,
while retaining exact owner approval, release eligibility, rollback baseline
and original CCC report. The direct manual *promote* path never catches it,
and still refuses the deployment. No checker check is marked PASS, no CCC
configuration is changed, and no image or root state is mutated.

## Operator and engineering acceptance

This is NOT a workaround for the installed root CCC checker. Deployment
still requires an independently authenticated, root-governed CCC checker
installation at the reviewed exact source, with backup, fingerprint and
readback verification; a canonical material change owner record; fresh full
pre-mutation CCC; and a root-governed breaker revalidation. Then the existing
owner-approved native release is subject to complete postmutation CCC, smoke
tests, rollback safety and evidence closeout.

A GitHub merge of this correction alone cannot fix the currently installed
worker: the root checker upgrade/bootstrap is a separate genuine external
authority dependency (issues #1517 and #1526). Until then, report actual
production as blocked rather than suggesting jobs are running. The 054
readmission and seven approved commitments must be separately measured.

Test contract: scheduled retries defer on the two exact checker patterns;
manual direct promotion still raises; all other CCC failures remain rejected;
release and owner metadata remain untouched by the deferral.
