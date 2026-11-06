# Owner Teams acceptance: fresh session after expiration (2026-10-18)

**Scope:** P0 #1545. Source-only, nonexecuting UAT session refresh. No deployment or Owner exact-SHA release authorization is implied.

## Confirmed previous outcome

The initial Owner UAT card was generated on 2026-10-17 at 23:53:05 UTC and its 10-minute authorization expired at 2026-10-18 00:03:05 UTC (8:03 PM Eastern on October 17). At 2026-10-18 09:31:38 UTC (5:31 AM Eastern), the registered Teams gateway recorded an authenticated callback rejected with HTTP 403, error code `approval_interaction_denied`. The existing approval ledger marked the prior request expired with no signed terminal decision. The runtime's ApprovalRequestService intentionally rejects any approval response after expiration. The generic Teams message is not proof of an identity-binding defect or a successful Deny.

## Fresh bounded campaign

- Change **only** the versioned test campaign's session ID to `OwnerUAT20261018Retry01` and campaign activation expiry to 2026-10-19 20:00:00 UTC.
- Keep `owner_identity_id=person-al`, AOT organization, test-only capability `interaction.owner.acceptance.record`, and `execution_permitted=false` unchanged.
- The existing immutable SHA-pinned manifest validator, exact recipient and owner identity binding, signed Teams callback, one-use approval repository, release-manager post-CCC/last-known-good guard, and protected release controls remain unchanged.
- This source campaign does not extend the individual card's **10-minute** response lifetime. The prior expired approval ID remains immutable and will not be reused.
- The first card explicitly asks the Owner to click **Deny**. Only a valid signed Deny can initiate a distinct **Approve** card. Neither action can execute a production, provider, ticket, client, PO, or device mutation.

## Release and live acceptance

1. Protected GitHub checks, security review, safe merge, then separate **exact final merge-SHA Owner production authorization** through the existing governance process. Earlier Owner approval of `e2d7577503ed0a3d8c06143b67478b9279d7aeeb` does not authorize a new commit.
2. Re-run canonical isolated preproduction with test worker OFF, verified rollback image/source matching, real post-exporter Grafana assurance, CCC, service-health/drift readback, and independent closed release record.
3. After governed deployment and closeout, retrieve actual test request/Teams send evidence. Owner personally confirms card is **visible** and clicks Deny before the 10-minute expiry. Confirm one authenticated denial receipt, then one distinct Approve card, the Owner's actual click, and an authenticated approval receipt.
4. Treat `accepted:` provider transport receipts as **delivery attempts**, not proof a human saw or clicked the card. Keep disputed release callback provenance (#1553) separate.
5. If the fresh card expires again, do not replay the approval ID or alter its timestamps. A new separately governed session must be issued.

**Status:** Ready for source validation only; no new Teams card claimed.
