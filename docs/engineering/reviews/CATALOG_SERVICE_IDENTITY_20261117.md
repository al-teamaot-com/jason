# Catalog service-identity correction — review candidate

Status: isolated source and transport tests only. No production change, no live
catalog write, no provider-backed acceptance claim. Owner requested preparation
and presentation before deployment on 2026-11-17.

## Problem and resulting behavior

The deployed catalog connector loads the dedicated `autotask.write` secret but
then forces provider-native impersonation of the authenticated requester.
The existing read authorization-mode setting does not affect this write path.

This candidate introduces deployment setting
`JASON_AUTOTASK_CATALOG_AUTH_MODE=jason_managed` for precisely:

- service.service.create
- service.service.update
- service.service.bundle.create
- service.service.bundle.update

These operations use the stored API integration credentials without an
ImpersonationResourceId header. Provider entity-permission preflight uses that
same account. Readback uses the same prepared credentials. The human remains
the authenticated principal in requester authority, exact-action approval and
audit. The setting neither grants requester authority nor supplies approval.

Absent configuration retains impersonation. An empty or unknown value fails
closed before provider access. Other procurement operations, tickets and reads
retain their existing behavior. No credential material is added to approvals:
only the API account username, execution mode and impersonation resource ID
are included in material execution-plan parameters. Changing those parameters
invalidates the approved plan; changing configuration after preparation also
blocks the pending execution. Existing enablement and approval gates remain.

## Isolated verification

63 tests passed: new catalog tests, existing procurement runtime and mutation
connector tests, ticket mutation connector tests and execution-plan binding.
Coverage includes all four catalog operations; service-account headers; requester
audit attribution; invalid mode; provider-access denial; write gate disabled;
readback ID mismatch; unchanged default/other-operation impersonation; and
changed execution account/mode causing zero provider writes.

Command, from implementation/runtime_service:

    python3 -m pytest -c pyproject.toml -o addopts= -q tests/test_autotask_catalog_service_identity.py tests/test_autotask_procurement_runtime.py ../connectors/tests/test_autotask_mutation_connector.py ../connectors/tests/test_autotask_procurement_mutation_connector.py ../orchestrator/tests/test_execution_plan_binding.py

No live provider request is made by these tests. Existing readback verifies ID,
not every submitted field; live acceptance must independently compare fields.

## Separate requester-configuration blocker

Prior live evidence showed NO_MATCHING_AUTHORITY_GRANT for the authenticated
Owner principal while catalog grants remained attached to legacy person-al.
The Owner administration allowlist also recognized only person-al. The code
change does not repair or bypass either condition.

The governed configuration proposal is to recognize the independently verified
Owner requester in the existing Owner allowlist, retaining the legacy entry,
and use authenticated authority administration to issue only the four catalog
grants above with approval_required=true and the existing AOT scope. Do not
remap identities, alter raw grant database records, or grant blanket access.
The exact grant records must be presented through the supported approval path.

The earlier local-Owner-only configuration recovery script is excluded from
this commit. Its sudo-TTY restriction remains; this change does not authorize
remote execution of that recovery path.

## Release and operational acceptance still required

This document is a source review, not a production deployment authorization.
Before requesting deployment, reconcile with the current release, build through
the governed release process, capture exact candidate artifact and rollback
artifact, and confirm the existing autotask.write credential belongs to Jason's
dedicated API-only account without exposing its secret. The source path proves
which credential profile is selected; it does not prove the live username or
Autotask account type.

Deployment scope: the catalog connector change plus the explicit catalog mode
setting and separately approved requester configuration. No unrelated feature,
ticket processing, PMv4, freeze, or promotion-hold changes are authorized.

Rollback: restore previous artifact and previous configuration through the
approved release mechanism. The inspected source base was
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63`; revalidate live state before release.
No production artifact was built by this preparation task.

Acceptance: confirm requester can request the four catalog actions; obtain an
exact approval for one specifically identified catalog mutation; perform it
through the normal governed MCP path; retain approval and execution correlation;
read the exact record back and compare every intended field. Confirm the provider
request had no user impersonation while the audit identifies the human requester.
A denied control request must produce zero provider writes. Any test-record
creation, cleanup or rollback mutation needs its own exact approved payload.
