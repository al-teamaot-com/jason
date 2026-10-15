# CCC post-deployment Prometheus target settlement

## Incident

During governed QuickBooks Production-read Stage 2 deployment on
2026-10-15, the exact candidate b906d9898f78db31026ef548cfeeb78c2355bb09
passed preproduction and reached production, including a successful governed
CompanyInfo read. The independent CCC check at 09:54 UTC reported
prometheus-targets: FAIL (healthy=13, total=14) while the exporter fleet
was being reconciled. All other CCC checks passed. The release correctly
rolled back to the verified Sandbox baseline. Prometheus later observed all
14 healthy, but brief scrape failures also occurred during the next isolated
preproduction verification, so this is not a fictional missing provider.

## Fail-closed repair

A transient sole failure of the Prometheus targets check in a **post-mutation**
CCC run can be rechecked with independent forced CCC reports at delays of
15, 20, then 25 seconds. The release-manager transaction lock remains held;
the checker cannot be substituted, its report must be fresh, complete,
uniquely identified and match candidate/runtime SHAs, and only a genuine
**new all-PASS report** can certify the release. No previous FAIL is rewritten.
If all attempts fail, the original CCC rejection still forces normal
rollback. Any failed source identity, authority, systemd, runtime, required
check, stale report, duplicate run ID, process/report inconsistency, or
unexpected checker error fails immediately. Pre-mutation admission remains
unchanged.

A successful retry records the identifiers of failed monitoring runs,
plus the retry count, in CCC postflight evidence for audit.

## Acceptance

Isolated tests reproduce 2 failed Prometheus checks before a fresh PASS,
persistent monitoring failures after the bounded allowance, nonmonitoring
failures, wrong SHA and repeated evidence IDs. All fail-closed source pin,
host reconciliation and rollback safety gates continue to apply.

**Not authorized to deploy by Stage 2's old exact-SHA approval.** The source
repair is a new protected core revision and requires separate CI, human
review, exact source approval and new isolated preproduction before deployment.
Keep it as a draft unless the production issue requires a new controlled
release. Never weaken CCC required-check thresholds to make QuickBooks pass.

Integration coordination: #1436, #1447, #1102.
