# 2026-10-17 P0 Teams approval: technical/security review and UAT release evidence

**Review type:** Jason/ChatGPT-assisted technical review of source and tests; **not an independent external human review, Owner authorization, CCC PASS, or live Microsoft Teams test**.

**Parent:** #1440 / #1545; disputed provenance #1553; containment #1554; combined draft #1557. This file records a bounded evidence snapshot and the remaining authorization gates.

## Reviewed source boundary

- Authoritative baseline `a30f6c392f0e1b74c64a948cdea49e7a4ceae43a`; combined **code** integration commit `79c36338c695c040cb6acf2cf29bec2569a48cd8` (from #1549, #1555 and #1556 at their exact tested heads). Adding this review document changes the overall PR commit SHA, not the reviewed code changes. **Owner approval must bind the final, subsequently verified exact SHA**, not an earlier partial SHA.
- Source changes: 36 paths including architecture and operations documentation, runtime composition, existing Teams gateway adapter, versioned universal interaction models, test-only owner flow, protected release containment, signed ingress callback route, and automated tests. `git diff --check` clean; no merge conflict; main and production unchanged.
- No new Teams OAuth app, bot, delegated Graph consent, transport, approval ledger, or provider execution authority. Existing registered Teams/Agents SDK gateway, identity binding, stored ApprovalRequest, audience routing, ApprovalInteractionDispatcher and one-use approval receipts are reused.

## Boundary-specific code and test review

| Boundary | Reviewed behavior | Evidence / residual condition |
| --- | --- | --- |
| Caller/recipient | Universal Interaction accepts provider-neutral requests, but a workflow authority, live Microsoft-to-Jason identity binding, audience review, exact AOT Owner recipient, and stored approval guard authorize the one delivery. | `teams_communication_service.py`, `universal_interaction/service.py`, `owner_uat.py`; tests for wrong scope, missing approval, wrong/expired actor. |
| Teams transport and replay | Existing `/internal/proactive/send` is the only transport used; the interaction journal claims before one non-idempotent send, never automatically replays a timed-out ambiguous send; provider acceptance does not claim notification, rendered card, or human click. | `teams_message_send.py`, `universal_interaction/teams.py`, `test_teams_communication_service.py`, `test_universal_interaction_service.py`. |
| Test approval issuer | Opt-in `JASON_OWNER_UAT_MODE=nonexecuting_test_only` plus worker flag and unique session; all off by default. Exact `owneruatapproval-` request, owner `person-al`, 600s TTL, `test_only=true` and `execution_permitted=false`; stored request prevents duplicate issuance. | `owner_uat.py`, `test_universal_owner_uat.py`; tests assert disabled default, one-shot, no release execution and no blind reissue. |
| Signed Teams responses | Signed registered-gateway envelope, exact action/decision, bound Entra tenant/actor, live active owner record, server-side immutable pending request and once-only approval receipt. An approval response creates **no executor capability**. | `conversation_ingress.py`, `owner_uat.py`, existing `ApprovalRequestService`; tests for wrong owner/tenant, tampering, callback/approval expiry, altered decision, denial, replay and nonexecution. |
| High-impact release hold | Strict regular 0600 protected policy, fail closed if malformed/symlink/insecure. Hold blocks release-card issue, signed callback and independent host receipt-to-CCC/release promotion; release watermark revokes pre-hold requests. It does not affect routine Teams or the harmless test. | `owner_release_approval_containment.py`, `mobile_release_approval.py`, `release_mobile_approval_consumer.py`, `release_manager_host_runner.py`; targeted hold, wrong-mode, immutable watermark and host tests pass. **A missing hold file preserves prior operation: source deployment is not activation.** |
| Cross-environment release proof | Protected host runner refuses consuming the default live signed-decision DB from isolated/preproduction release state roots. Subsequent exact SHA, CCC, rollback and root-host verification remain separate from card receipts. | `release_manager_host_runner.py` and focused release consumer/host tests. |

## Executed verification

1. In an isolated, clean worktree, combined Python UAT/interaction/Teams/ingress/composition tests completed with pytest exit 0. Imports of `jason_runtime`, `jason_openclaw`, and `connectors` were confirmed to resolve to the integrated candidate checkout (initial missing `PYTHONPATH` attempt was harness setup, not a code failure).
2. Combined protected release containment/mobile/host-consumer tests completed with pytest exit 0 (including the corrected signed callback expiry fixture in #1556).
3. Supplemental host-release validation across five suites: **121 passed, 9 subtests passed, 3 failed**. The exact same three `test_release_manager_atomic_surfaces.py` fixture failures reproduce on untouched main baseline `a30f6c392` (missing valid `release_manifest`/`risk_profile`) and are **pre-existing debt**, not candidate regressions. Do not assert the full optional host suite is green; maintain separate repair scope.
4. Constituent PR protected CI: #1549 8/8 successful, #1555 9/9 successful, #1556 4/4 successful. The combined draft PR #1557 must pass **its own** protected checks; initial GitHub `Validate Jason` failure concerned mandatory PR documentation impact and overlapping active PR acknowledgement. Both are recorded in #1557's body and must be reverified on the new exact PR head.
5. Concurrent overlap reviewed/recorded, not silently merged: included #1549/#1555/#1556; unrelated draft #692 finance, #1331 matching, and optional OAuth #1548 have active overlapping filenames and must rebase/retest in their own workstreams.

## Residual P0 security and release blockers

- **Provenance:** #1553 documents a signed legacy owner-account callback without Owner-confirmed visibility/click. A signed Bot Framework/gateway event is **not** a proof of physical person pressing Approve. The disputed callback remains a security escalation. Do not convert it to owner approval, even if release source, CCC, or Teams message text exists.
- **Live containment:** #1554 hold mechanism is source only. Before trusting high-impact release approvals, independently verify reviewed policy activation at protected root scope and owner confirmation of the chosen safe alternate authorization route. Do not change root 0600 files manually from this review.
- **Authority:** No owner exact-SHA release/CCC approval has been granted for the integrated UAT source. Owner's agreement to prioritize the test does not sign a final commit or allow self-approval. The Owner should only need a concise explicit exact-hash risk decision through an already authorized route, not manual source review or routine SSH.
- **Activation:** harmless owner UAT remains off. Do not activate or issue a live Teams card without the existing authorized production/release path. A successful Python test/CI or provider-accepted message is not live owner acceptance.

## First real acceptance proof (after governed activation)

1. Confirm running revision, protected CCC/readback, exact configured session and owner identity, existing Teams app delivery route, no unexpected impact. Keep ordinary Universal Approver and high-impact actions off.
2. Issue exactly one clearly labeled `TEST ONLY / NO EXECUTION` Teams card. Ask the owner to confirm **visibly receiving** it on intended device and personally press **Deny**. Verify provider message ID, incoming signed activity, active owner binding, request scope, unique terminal DENIED receipt, absence of execution.
3. Issue **a different unique session**, show the same nonexecuting details, owner personally presses **Approve**. Require one terminal APPROVED receipt, signed callback and independent owner confirmation, still **no execution**.
4. Verify tampered/expired/wrong-tenant/duplicated/replayed responses cannot authorize or reissue; distinguish `provider accepted`, `human saw/clicked`, `decision recorded`, and `actual execution`.
5. Only after both tests pass should broader per-workflow rollout be considered under separate risk and owner authority policies. The production Universal Approver is **not accepted by this review**.

**Status at writing: TECHNICAL SOURCE / REVIEW PACKAGE PREPARED; OWNER RELEASE AUTHORIZATION AND LIVE HUMAN UAT NOT COMPLETED.**
