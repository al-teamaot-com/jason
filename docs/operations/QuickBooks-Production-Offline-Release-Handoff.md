# QuickBooks Production read activation: Git hosting outage handoff

Status: **local engineering only**; not an approved production deployment.
Prepared October 13, 2026 for AOT Project Jason. This file records verifiable
local source and acceptance gates without substituting for protected release
authority. It contains no client secrets, OAuth tokens, or accounting balances.

## Current source and deployment

- Last locally known merged base: `e3b80f80df54fd9f92afa93d721980e522f5fa37`
  (PR #1329; original Production profile declaration and rollback fix).
- Offline QuickBooks branch:
  `integration/quickbooks-production-acceptance-20261013`
- Local ordered commits on top of base:
  - `3b89384e`: standalone governed CompanyInfo acceptance evaluator
  - `b8564c52`: actual Runtime/MCP Docker readback and fresh OAuth requirements
  - `8e986fc8`: reject cross-environment tokens before OAuth refresh
- Deployed Runtime and MCP are still at
  `2087dd3898b17638659c8f975006290e4f2951c2`, with
  `quickbooks-sandbox-read-v1` in both. No Production profile is activated.
- Production OAuth state is independently stored and realm-bound. The access
  token was expired at last inspection; there is a refresh token, but that
  **does not** prove its current usability.
- Production GitHub fetch/check-runs returned 403 account suspended.
  GitHub Support case #4852724 exists; do not file a duplicate ticket.

## Offline validation completed

Run focused tests from the local branch:

```sh
cd /home/al/jason-worktrees/quickbooks-production-acceptance-20261013
PYTHONPATH=implementation:implementation/runtime_service/src \
  /home/al/projects/jason/.venv/bin/python -m pytest -q \
  tools/tests/test_quickbooks_production_read_acceptance.py \
  tools/tests/test_quickbooks_production_profile_release.py \
  implementation/runtime_service/tests/test_quickbooks_read_activation.py \
  implementation/connectors/tests/test_quickbooks_oauth.py \
  implementation/connectors/tests/test_quickbooks_connector.py \
  implementation/release/tests/test_quickbooks_production_deployment_mount.py \
  tools/tests/test_provider_secret_provision.py
```

These tests passed locally on October 13. They do not prove live Production
connectivity, authorized CI, merged upstream status, or a production cutover.

## Release-authority migration requirements

Do **not** change Git remote to an unverified replacement or edit release
records to imitate CI success. A trusted Azure DevOps/other failover must first:

1. Establish AOT owner-controlled repository identity, authentication,
   immutable commit ancestry and enforced protected-branch reviews.
2. Import the existing known commit history without losing parentage.
3. Define an independent trusted CI system with required equivalent checks.
   The exact names, acceptance results, runs, candidate commit SHA, and
   timestamp must be independently queryable and tamper-evident.
4. Add a reviewed and tested source-and-checks authority adapter to the
   Release Manager, not a skipped GitHub verification.
5. Require an explicit owner-signed/recorded authority-switch decision for the
   exact release; default to fail-closed on missing evidence.
6. Retain independent CCC, live drift guard, image digests, exact-SHA owner
   approval, pre-production, rollback to both prior images and Sandbox profile,
   host-reconciliation gates, and an audit trail.
7. Roll out the authority adapter using an approved bootstrap and rollback
   procedure. The existing runner does *not* support Azure failover today.

Until those gates are independently approved, all changes stay offline.

## Required QuickBooks cutover sequence

1. Confirm authoritative approved source, Git/alternative CI evidence,
   independent CCC, root service health, and exact release SHA. Re-run tests
   after branch reconciliation; local success alone is not production evidence.
2. Stage the Release Manager/controller safety change while **retaining**
   Sandbox in both deployed services. The original merged source declares
   Production, so explicitly prove stage one retains Sandbox; do not assume.
3. Read back both running containers' source revisions, profiles and health.
4. Prepare and approve a *separate* immutable Production profile release.
5. Deploy with canonical Release Manager. No direct Docker env manipulation,
   alternate Intuit API reads, ungoverned token refresh, or accounting writes.
6. Call Jason MCP's governed `accounting.company.read` and confirm it returns
   the live AOT QuickBooks company. This is the first controlled refresh
   opportunity for the stored Production refresh token.
7. Collect fresh non-secret `quickbooks_oauth.py status --environment production`
   and original governed read evidence; use the source's
   `quickbooks_production_read_acceptance.py` to validate live profile, OAuth,
   service source alignment and company identity. Retain correlation ID.
8. Complete independent CCC, drift, rollback-readiness and post-deployment
   gates. If connectivity or any check fails, use canonical rollback and
   restore Sandbox; if refresh grant is invalid, request owner reconnect.

Never declare QuickBooks Production working from the mere existence of
production credentials, access to Sandbox, or locally passing tests.
