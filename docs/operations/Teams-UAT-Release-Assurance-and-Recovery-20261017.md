# Teams UAT governed release recovery — 2026-10-17

**Parent:** P0 #1560; acceptance #1545; activation PR #1559. **Status:** SOURCE FIX PROPOSAL — NOT PRODUCTION APPROVAL.

## Observed incident and evidence

The exact-SHA Owner-approved nonexecuting UAT release `351d8716a26b6065585f8ca8ee587ffa634cd7c2` cleared all required protected CI and isolated preproduction, with its owner approval and material CCC review recorded via the Release Manager. During promotion, the root host reconciler restarted exporter services and an independent scheduled `jason-grafana-assurance.service` check ran while usage-attribution metrics were temporarily unavailable. The check truthfully recorded `DRIFTED`; the production drift guard subsequently found the failed system unit and refused successful release closeout.

After exporter service recovery, independently queried Prometheus metrics (usage attribution `up=1`, OpenAI usage/cost source `=1`, available cost MTD) and the unmodified scheduled Grafana assurance checker returned **PASS** at 23:10:26Z. The failure was transient, but the root host reconciliation correctly failed on its evidence available earlier. **No assurance failure was waived**.

The existing Release Manager attempted reverse-order automatic rollback to the immutable last-known-good `0dceb0af7498e14fedb35aca71b35ed0a95e2526`. The new candidate's `production-deploy.sh` tried to authenticate `config/owner-uat-campaign.json` against that old SHA, which never contained the new manifest. MCP and host recovered, but runtime rollback failed and left a mixed revision. No UAT card was sent because the runtime's root-verified closed-release gate remained false.

The owner-approved rollback was recovered with the exact root-owned previous release script and previous release image; the preflight, hardening, runtime health and revision verification all passed. All live runtime/MCP/host revisions now match `0dceb0af7498e14fedb35aca71b35ed0a95e2526`; runtime UAT is OFF; the root-governed circuit breaker was independently revalidated CLOSED at 23:13:55Z.

## Corrective controls

1. **Manifest-less LKG compatibility.** The candidate canonical runtime deploy script recognizes only the existing Release Manager's `jason-runtime:rollback-current` tag as a rollback. It checks that the immutable image's embedded source label is exactly the 40-hex revision requested. Only then does it force `JASON_OWNER_UAT_MODE=off`, worker false and session empty. It does not require a manifest that never existed in that old revision. Any image/source mismatch is rejected. Ordinary forward deploys must still verify the exact reviewed SHA's Git-blob manifest and the limited AOT nonexecuting campaign schema.
2. **Genuine post-exporter assurance.** After exporter service verification and observability reconciliation, before final production drift guard, the reconciler re-executes the original `jason-grafana-assurance.service`. A maximum of three bounded attempts may allow exporters and Prometheus scrape series to stabilize. The actual checker must return success; no `reset-failed`, policy relaxation, dummy metric, synthetic PASS, or ignored exit is allowed. Genuine missing telemetry still rejects the release.
3. **One issuer.** Only the autonomy maintenance child may issue the nonexecuting UAT card. The request-serving HTTP process keeps its signed Teams response handler, but the owner test worker is explicitly off there. The maintenance child is started when the test-only worker is opted in, even if other background workers are disabled.

## Verification before any production attempt

- Reproduce automatic rollback behavior with a disposable fake deploy invocation that uses the real candidate canonical script but mocks all provider/Docker actions; demonstrate flags OFF when rollback image label equals prior SHA, fail-closed on mismatch, and no rollback shortcut for normal forward image tags.
- Reproduce the scheduled Grafana assurance startup race with disposable mock `systemctl`, `timeout` and `sleep`; require a REAL checker success to exit zero; after three failed checks return nonzero; a second attempt returning PASS must succeed.
- Validate the UAT maintenance/HTTP worker isolation, exact source-gated campaign, signed DENY then distinct APPROVE, replay and expiry rejection, and no provider execution.
- Run targeted and existing regression tests, protected PR GitHub checks, production-control constitutional review, exact reviewed PR merge and **new exact-merge-SHA Owner release authorization**. The earlier `351d8716...` approval does not transfer to a new commit.
- Complete official preproduction, host/release CCC, root reconciler, drift verification, rollback and closed root last-known-good readback **before** one test card is issued. Confirm real owner personally sees/presses buttons; a signed callback alone is not proof of their action.

## Scope limitations

This is an infrastructure reliability correction for a TEST ONLY, no-execution Teams acceptance workflow. It does not clear the disputed human-click provenance #1553, authorize high-impact release approvals, restart client devices, or broaden current release/procurement/Autotask authority. AOT's authorized Owner retains the exact-SHA production decision.
