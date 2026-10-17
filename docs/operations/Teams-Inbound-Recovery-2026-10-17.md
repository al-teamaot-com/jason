# P0 Teams inbound conversation recovery

**Status:** Minimal source hotfix for independent governed review. Not deployed.
**Date:** 2026-10-17
**Parent:** UTA P0 #1440/#1545 and canonical PR #1549.

## Production incident: two independent fail-closed problems

1. A Teams user message requesting a GitHub code review included a PR link
   and finance examples. The existing broad procurement URL classifier
   incorrectly sent it into the procurement product URL handler.
   Audit correlation: `41d50575-ac33-4945-a4d8-f959a7faab83`.
2. Even an ordinary **no-URL** Teams review request failed with
   `MicrosoftBoundaryError / MICROSOFT_PROFILE_NOT_APPROVED`.
   Audit correlation: `a02ff53d-53ab-4fcf-a4ee-999874d9f63b`.

The original production code at `f7f33cf6d7133dabb1d30cb78ef73dd8b0524c75`
set its common Microsoft Graph identity-directory reader to the expanded
`identity-investigation-read` profile. Production's durable and validated
AOT `microsoft_graph` client boundary is intentionally `directory-read`.
The additional profile demands separate Microsoft consent; it must not be
assumed or silently granted. No new user identity, secret, OAuth application,
tenant grant, or role change is needed for normal Teams messages.

## Bounded repair (no new capability)

- Restore the existing `directory-read` profile at both Microsoft directory
  token-provider layers, leaving the `identity-investigation-read` catalog
  available separately pending controlled tenant/admin consent.
- Exclude non-commerce source-control/docs hostnames from automatic procurement
  URL pickup. Use whole-word procurement intent instead of loose substring
  matching. Maintain standalone vendor HTTPS product-link and explicit purchase,
  invoice, quote, part and Autotask-ticket behavior.
- No changes to Teams gateway authentication, SDK, trusted identity bindings,
  approval rules, Autotask writes, OpenBao secrets, provider authorizations,
  J-002/ADR-009 governance or any production worker configuration.

## Verification and rollout gates

- Confirm exact GitHub candidate and independent regression/architecture
  review. Run existing OpenClaw conversation, Microsoft token/boundary, runtime
  composition, Teams gateway and security CI suites.
- Validate a synthetic narrow directory boundary succeeds using a stub token;
  test expanded-only profile **fails closed**. No Graph tokens issued in tests.
- Validate signed generic Teams messages mentioning GitHub PR, finance nouns
  and source links use **conversation ingress**, not procurement; actual vendor
  product links continue to use procurement.
- After **Owner approval for the exact SHA**, deploy via the existing governed
  Release Manager (CCC, rollback, host reconciliation, protected drift).
  Never alter the live SQLite boundary, disable Graph profile checks, forge a
  Teams approval, or bypass a release check.
- After deployment, ask Jason to read-only-review canonical UTA PR #1549 from
  Teams without a web URL. Confirm authenticated message, successfully bound
  identity, response, and review findings. Verify invoice/PO card routing and
  existing release approvals still function. Unverified Approve/Deny remains
  outstanding for universal acceptance.
- Preserve exact rollback revision and audit. Do not claim success until a
  real inbound Teams message and governed readback both pass.

## Concurrent-source protection

Open PRs #1331 **and #692** contain the opposite, unrelated expansion of
the same common directory profile. Their finance scope is not authorization
to broaden AOT's Microsoft Graph consent. Exact patches in both were reviewed
and coordination comments recorded. PR #692 also overlaps the older
procurement/billing conversation-ingress implementation; no merge should
overwrite the canonical signed Teams entrypoint or this bounded URL classifier.
Preserve the narrow profile until a separately approved entitlement and
distinct investigative reader are provisioned.

PR integration reconciliation must appear on the **first**
`Integration coordination:` line of the live GitHub PR body. Jason's
`change_integration_gate.py` deliberately parses the first matching line,
not appended later acknowledgements. The explicitly reviewed concurrent
PRs for this recovery are #692, #1331, #1548, #1440, #1545 and #1549.

The synthetic owner-only mobile-release tests also used a fixed time in the
past, causing false expiry failures in unrelated CI jobs. This hotfix adopts
the existing established rolling test-time fixture. It does not change
actual release expiry, release policy or approval execution behavior.
Draft PR #1548 includes the **same exact test-only timestamp fix**; its
OAuth-first approval architecture remains explicitly out of scope and in
draft. That overlapping fixture must be retained once, not treated as a
reason to merge an unapproved second approval architecture.
