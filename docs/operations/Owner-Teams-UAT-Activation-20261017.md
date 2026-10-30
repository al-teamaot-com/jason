# P0: Release-governed activation of the nonexecuting Owner Teams test

**Status: isolated SOURCE CANDIDATE, NOT yet authorized, released, activated, or owner-tested.** Parent: #1545 and #1440. Source follows the existing signed Teams gateway and Universal Interaction Service deployed in #1557.

## Immutable activation scope

The candidate release includes a source-tracked, bounded `config/owner-uat-campaign.json`, read exclusively by the existing canonical `infrastructure/jason-runtime/production-deploy.sh`. Its `tools/owner_uat_activation.py` validator verifies the on-disk manifest bytes against the exact Git commit blob provided by the existing release manager; it fails closed on an unknown field, tampered source, unsafe identity, non-test capability, missing UTC expiry, or a campaign lasting more than 48 hours.

Only these three existing runtime settings are allowed:

- `JASON_OWNER_UAT_MODE=nonexecuting_test_only`
- `JASON_OWNER_UAT_WORKER_ENABLED=true`
- `JASON_OWNER_UAT_SESSION_ID=OwnerUAT20261017Pilot`

The source-committed campaign automatically becomes OFF after `2026-10-19T00:00:00Z` **at activation/deploy time**; no other workflow modes, owners, credentials, capabilities, providers, or privileges can be changed by this parser. In particular `JASON_UNIVERSAL_APPROVAL_MODE` stays OFF and the existing owner-only release pilot remains independent. Do not infer that a source-committed campaign is permission to bypass exact-SHA human production authorization or CCC.

## Release and runtime boundary

1. The isolated PR must receive independent source/constitutional review, exact-head CI, safeguarded merge to main, and **separate Owner exact-final-SHA production release approval**; the original #1557 SHA is not authorization for this new SHA.
2. The **existing Release Manager** builds and checks artifacts, validates the new SHA, runs isolated preproduction (where the three Owner UAT settings are forcibly OFF), checks the protected core, invokes canonical production scripts, performs host reconciliation and post-mutation CCC, verifies rollback and closes the release.
3. The existing runtime registers its test-only signed callback and one-shot worker only if the allowed manifest was present at the exact reviewed SHA during canonical deployment. No manually patched live container, direct API, unregistered bot or parallel approval ledger is permitted.
4. The test-only worker checks that the **same exact runtime SHA** has a closed Release Manager record, matching original Owner approval, passed post-mutation CCC, aligned runtime/MCP/host/release-manager revisions, and the separate protected root readback showing a closed breaker and the exact last-known-good revision. Until all match, it does not send any card. Malformed, missing, or insecure evidence also blocks issuance.
5. When ready, it sends exactly one existing-workflow Adaptive Card to `person-al` in Teams, marked `TEST ONLY: NO EXECUTION (1/2: DENY)`, with 10-minute expiry. Only a real signed owner **Deny** receipt permits the second, distinct session `OwnerUAT20261017Pilot.approve` to be sent with `2/2: APPROVE`. A first-card Approve, expiry, unknown send, altered click, or duplicate cannot advance the two-step test.
6. Both button actions only persist immutable test receipts for `interaction.owner.acceptance.record`, with `execution_permitted=false`. No release/CCC, ticket, procurement, provider, device or service mutation can be sourced from either result. As required by #1553, the owner must **personally confirm visible card delivery and the button clicked**; a signed SDK callback or provider accepted transport alone is not proof of physical presence.
7. Confirm both real-world decisions, sender/user/tenant binding, actual Teams message ID, one-use signed receipts and no execution. Do not label the broader Universal Approver working until the remaining high-impact provenance/containment controls are proven.

## Disable/expiry and rollback

The campaign is **one-time**; its stable hashed approval IDs and the existing durable delivery journal prevent resends after provider ambiguity or runtime restart. Removal or disabling of the source-committed manifest in a separately approved future release forces all three environment values OFF via the same canonical script. The original release rollback process must restore the preceding runtime shape and configuration if any new deployment step fails; no direct live environment override is an approved activation, recovery, or rollback. Once the campaign expires, it will not activate on a subsequent deploy; the previously created 10-minute card still expires normally and cannot be extended.

Review source: `tools/owner_uat_activation.py`, `infrastructure/jason-runtime/production-deploy.sh`, `tools/release_manager_host_runner.py`, `implementation/runtime_service/src/jason_runtime/universal_interaction/owner_uat.py`, `implementation/runtime_service/src/jason_runtime/composition.py`, plus targeted tests.
