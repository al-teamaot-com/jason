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

## Second same-SHA reissue: bounded exporter ownership recheck

The governed `release-b906d9898f78db31-retry-1` was separately prepared,
preproduction verified and Owner-approved under the SAME exact candidate
SHA. The host reconciler again failed, this time before CCC, at the
`system_service_activation` step. The full root-owned reconcile result
`release-b906d9898f78-e2da75c2a706.json` proves that its managed Git
sources were reconciled successfully; the release record's short error
excerpt was truncated. During exporter activation systemd reported
`Warning! D-Bus connection terminated`; the strict port-ownership guard
then correctly rejected `jason-status-exporter.service` because TCP
port 9464 had no listening owner and `MainPID=0`. The attempt performed a
verified rollback to Sandbox LKG `5c65cde7`.

The host script now allows up to two *explicit* bounded restarts of a
candidate stateless exporter only for the precise guard failure
`has no listening owner (MainPID=0)`. Before each restart, the SAME
independent port guard must prove its socket is entirely free.
`systemctl restart` is bounded with a 25-second timeout; the matching
owned-port probe must then PASS. All missing/unrecognized ownership,
occupied socket, nonzero MainPID with no listener, permanent D-Bus failures,
non-allowlisted unit, or repeated failed restarts still cause the host
reconciler to fail and the release manager to execute normal rollback.
This procedure cannot kill a socket owner, change unit allowlists, or
count a different process as the exporter.

Regression tests run the extracted live shell helper against isolated
mock port guard, timeout, systemctl and sleep binaries, covering a
single startup gap, foreign port owner with no restart, and persistent
listener absence after exactly two bounded restarts.

This combined CCC/host repair requires a fresh reviewed source SHA, all
protected CI, preproduction and explicit Owner approval before ANY live
deployment. Do not reuse the older exact-SHA approval and do not edit
root-owned state or source by hand.
