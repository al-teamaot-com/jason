# AOT Client Information Request Library — Round 1

## Section Goal
Preserve the Owner-approved wording of 120 generic client information requests (JQ-001 through JQ-120) and the standard AOT support footer as immutable, versioned source data, without publishing or enabling an autonomous sender.

## Status / production boundary
- **Content:** Owner approved Round 1 in chat on 2026-10-28.
- **Operational sending:** NOT activated; all 120 entries have `autonomous_send_enabled=false`.
- **Production freeze:** ACTIVE. No merge into protected main, PM prepare/promote, profile changes, live ticket updates, or client notifications under this change.
- The current `config/client_communications/approved.json` is intentionally unchanged.
- This is a reviewable **content package**, **not** a working automatic question-selection or outbound-notification feature.

## Package
`config/client_communications/information_requests_round1.json` contains:
- 120 stable IDs `JQ-001`–`JQ-120`;
- title, exact wording, category, review class, content approval, and disabled sending;
- separate `client-support-footer-v1` with AOT support email and phone;
- bounded `{{ticket_number}}` token for eventual verified render-time substitution.

## Required implementation before any activation
1. Decide deterministic question-eligibility evidence and which categories need technician review. A content approval never overrides playbook-level authority.
2. Extend the existing approved message registry/renderer **without altering current VulScan exact-body behavior**. Render only approved text and bounded, validated ticket-number substitution; append footer exactly once. Reject unknown placeholders, changed wording, cross-company contact, and arbitrary recipients.
3. Read ticket notes/history and available diagnostics before asking. Deduplicate by ticket, question ID, material evidence and pending client response, not just body text.
4. Require exact workflow/template binding, governed `service.ticket.client.notification.create`, authoritative ticket/contact match, contact email enabled, post-write ticket-note readback, and notification history verification where needed.
5. Track waiting-for-client state and resume the approved playbook on a genuine client reply without repeatedly nagging or claiming a resolution.
6. Add tests for exact full composition, escaping and token validation, authorization rejection, high-risk escalations, concurrent sends, idempotency, readback, and resumed work.
7. Review overlapping open PRs, reconcile current protected main, and obtain required protected checks. Do not auto-merge.
8. **PM controls release** under the active freeze; only a separately authorized exact-SHA freeze exception and governed release process may enable this work.

## Safety
Never expose internal system names, secrets, unverified claims, or private evidence in the client's question. Do not ask clients for passwords or MFA codes. A request for timing/approval is not itself approval for disruptive work. Security/backup/permissions questions require case-appropriate governed checks.

## Test
`python -m pytest implementation/runtime_service/tests/test_client_information_requests_round1.py` from repository root with pytest available.

## Rollback
Delete the staged catalog, documentation and source-only test on this branch if rejected. Existing live message registry and production runtime remain unchanged.
