# P0 #1440 - bounded owner Teams Deny/Approve acceptance campaign

**Type:** Source-pinned, nonexecuting Owner UAT; **not** a live approval for reboots, purchasing, ticket changes, protected releases or other customer/provider actions.

## Live starting point (October 23, 2026)

Production is running exact immutable SHA `743c75eaa541dfcb1efb1cd80746728395fcfe97`. Teams status messages arrive, and previous nonexecuting Owner UAT ledger records contain signed `microsoft_teams` receipts (two Approve and one Deny). The **generic** `JASON_UNIVERSAL_APPROVAL_MODE` is off, and no universal approval policy/database was installed. `JASON_OWNER_UAT_MODE` and its maintenance worker were off because the previously source-pinned `owner-uat-campaign.json` expired October 22. Historical test receipts do not prove the generic Universal Approver works today. The provenance dispute in #1553 remains open; signed evidence is not proof of the physical owner's action.

## Verified and fixed activation boundary

The production release package at `/opt/jason/releases/<exact_sha>` deliberately has **no `.git` metadata**. The original `owner_uat_activation.verify_source_pinned_manifest` tried to run `git show` in that directory and would reject an enabled campaign. The correction accepts ONLY a source path in a trusted developer Git worktree or the exact immutable `/opt/jason/releases/<approved_sha>` package, and verifies the small manifest **byte for byte** against `<approved_sha>:config/owner-uat-campaign.json` read from Jason's existing managed source repository. A changed or unavailable Git blob, mismatched SHA, symlink, world-writable manifest, unknown field or broadened scope fails closed.

This branch renews ONLY a short-lived test-only campaign:
- `session_id=OwnerUAT20261023SafeDenyApprove01`
- `expires_at=2026-10-25T17:00:00Z`
- `owner_identity_id=person-al`
- `requester_identity_id=svc-jason-acceptance-test`
- `organization_id=aot`
- `capability=interaction.owner.acceptance.record`
- `execution_permitted=false`

The manifest parser refuses campaigns more than 48 hours ahead and returns mode off once expired. Preproduction remains off. No unapproved runtime env editing is permitted.

The deployed `OwnerUatReleaseGate.ready()` was executed read-only **inside the running production container** for its exact closed production revision and returned **True**. The gate requires the current exact-SHA root-protected release closeout, live runtime/MCP/host identities, post-deployment CCC PASS and closed breaker. For a new release, the worker will remain inert until that separate exact-revision release is certified and closed.

## Actual Owner live acceptance (after governed new release only)

1. Runtime composes the existing signed Teams gateway, already-provisioned Owner binding, shared Teams approval ledger and signed callback route in **nonexecuting_test_only** mode. No new Teams bot, separate OAuth provider, standalone approval endpoint or provider executor.
2. A one-shot maintenance cycle creates **one** `TEST ONLY` card. Owner separately verifies its visibility in the expected Teams chat, notification (if applicable), and buttons, then clicks **Deny**. The callback must present the authenticated Microsoft tenant/object, exact signed `approval.submit`, unexpired pending immutable request, authorized Owner, unique response id and normal replay ledger. The durable decision must become `denied`; no provider mutation.
3. Only after a **real signed Deny receipt** does the maintenance cycle issue the second distinct `TEST ONLY` card. Owner sees it, clicks **Approve**, and independently confirms having done so. The durable decision must become `approved`; no ticket, purchase, reboot, protected release or customer action.
4. Verify actual Teams message identifiers, registered gateway response identifiers, signed callback identity, immutable scope, replay/expiration refusal and that only **one** test receipt is present for each card. Do not infer clicks from send acceptance or from historical callback provenance.
5. Leave high-impact new approval issuance blocked until #1553 callback provenance is resolved and the shared `JASON_UNIVERSAL_APPROVAL_MODE=enforced` path has versioned, least-privilege role/tenant policy and real two-requester/two-approver acceptance. This source campaign **does not activate the generic Universal Approver**.

## Required release gates

Source PR review/tests and all protected CI on the exact SHA, native isolated preproduction including rollback readiness, fresh authenticated Owner approval and matching CCC material review for the **new release SHA**, and native governed deployment/CCC/root-LKG verification. Previous release approvals do not transfer. Preserve current automatic promotion incident hold and historical failed release records. If the test window expires before approval, **do not manually override it**; a new reviewed exact-source campaign is required.

AOT has no second local code reviewer; document technical security findings and protected automated checks without falsely claiming an independent human approval.
