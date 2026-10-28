# AOT Client Information Requests — Round 1 Production Handoff

Owner content approval: 2026-10-28. Status: NOT DEPLOYED. Production freeze: ACTIVE.

## Implementation inventory

- Approved source: config/client_communications/information_requests_round1.json — all 120 stable JQ identifiers and distinct source-controlled gap codes, classifications, exact wording, and footer.
- Deterministic question selection, safe ticket-reference rendering, durable SQLite reservation, and reply reconciliation: implementation/runtime_service/src/jason_runtime/client_information_requests.py.
- Exact approved server-side message reconstruction: approved_client_messages.py and autotask_client_notification.py. Original VulScan fixed-body path is preserved.
- Optional autonomous-worker integration: autonomy_worker_runtime.py and autonomy_worker_composition.py. Verified same-company contact reply can resume exactly the suspended authorized phase.
- Feature-specific read-only information-release policy: implementation/orchestrator/autotask_information_authorizer.py. Does not broaden the normal autonomy-worker read allowlist.

## Security / activation

Source approval grants NO communication or production authority. This feature is disabled unless all conditions hold:
1. A separate exact-SHA governed release through Production Manager after an Owner-approved exception to the production freeze.
2. Existing approved-workflow client notification profile.
3. JASON_CLIENT_INFORMATION_REQUEST_PROFILE=approved-round1-v1.
4. Durable Owner promotion for client_information_request v1.0.0, policy playbook-autonomy:client_information_request, including service.ticket.client.notification.create.
5. A promoted diagnostic playbook supplies an exact catalog gap code, corroborated evidence fingerprint, and verified ticket identity.
6. The outbound question is classified routine. Context-controlled and human-review questions require a separately designed exact technician-review authority and cannot presently be auto-sent.

No freeform questions, passwords, customer-selected recipients, or unverified ticket-number substitutions. The connector rechecks exact ticket/contact company, email notification preference and exact reconstructed title/body. Uncertain writes never auto-retry.

## Durable lifecycle

Read authoritative ticket, contact, notes and notification history. Reserve question+ticket+evidence before any write. Send the canonical approved question and footer containing support@teamaot.com, 757-466-8862 and a validated ticket number. Require published-note readback and a matching recipient notification-history event before awaiting a reply. Only a newer same-contact authored note can resume a suspended workflow, with exact original phase and company rechecked. Ambiguous responses stay pending.

## Remaining production-readiness work

- One strictly bounded automatic intake path is integrated: an exact client-created ticket in Jason's queue with no description, no linked operational work, and a current matching ticket contact may request JQ-001 after the authoritative ticket and notes reconfirm no description. A verified reply returns it to the ordinary queue assessment cycle.
- Other diagnostic playbooks do not yet emit their missing-information gap codes. Pilot integration into real diagnostic branches and controlled live acceptance must be demonstrated before calling all real-world paths complete.
- Full local runtime suite passed when run with an isolated empty Datto component-approval registry. Seven unrelated Datto tests fail on the Jason host if they read its live durable approval registry; the failures reproduce on untouched protected main and pass with an empty isolated registry. Do not modify the live registry or Datto approval safety rules to satisfy tests.
- Complete required GitHub protected checks and independent review; local test success alone does not certify production.
- Reconcile against current protected main and overlapping work, then merge through the protected process.
- Production Manager must report exact candidate SHA, separately verified LKG/rollback SHA, all unrelated commits and files, authenticated foundational read canaries, RMM/Teams results, preproduction and rollback-readiness evidence.
- Do NOT deploy, activate, restart production containers, or remove the production freeze without a separate exact-SHA Owner decision.

## Reversibility

Feature profile is off by default. Use native PM rollback to a verified immutable release when subsequently authorized; preserve the SQLite evidence ledger and existing messaging behavior.
