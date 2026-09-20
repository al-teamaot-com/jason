# Jason Procurement / Mail Read Checkpoint — 2026-09-20

## Section Goal

Build and operationally stage a governed procurement lifecycle that can distinguish ordered quantity from customer-billable quantity, associate purchases to the correct Autotask ticket using ticket number + title, preserve AOT inventory allocations, monitor approved requester/vendor mailbox evidence, and route financial/material changes through approval.

## Current status

**ACTIVE / PARTIALLY PRODUCTION-PROVEN.**

The procurement foundation is live. The mailbox-evidence path is source-ready but remains intentionally dormant until the separate Microsoft application and Exchange Application RBAC scope are provisioned and accepted.

## Production-proven capabilities

- Governed Autotask product, product-vendor, service, service-bundle, purchase-order, purchase-order-item, and receive actions are live.
- Ticket charge search/read/create/update is live; create/update remain high-risk and approval-gated.
- A bounded live `service.ticket.charge.search` against controlled ticket ID `7680` succeeded with correlation `corr_mcp_ceb63529e09740178e74c797bd3851b3`.
- Procurement line allocation is deterministic: ordered quantity must equal the sum of all explicit destination allocations.
- The canonical acceptance example is `2 ordered = 1 customer/ticket + 1 AOT inventory`; billable quantity is `1`.
- Ticket candidates must be presented as `ticket number — title`.
- PO/ticket association does not grant billing authority. Ticket billing is a separate governed financial decision.
- `direct_provider_access=false` remains preserved.

## Mail-read implementation checkpoint

Source includes:

- `communication.mail.message.search`;
- `communication.mail.message.read`;
- `communication.mail.attachment.search`;
- exact approved-mailbox allowlisting;
- separate logical secret `microsoft_graph.mail_read`;
- separate OpenBao AppRole/runtime mount contract;
- separate `microsoft_graph_mail` boundary/profile `mail-read`;
- explicit provider-read v6 profile;
- Exchange Application RBAC model using `Application Mail.Read`;
- no tenant-wide Entra Graph `Mail.Read` grant;
- dedicated public certificate, with private key retained outside the repository.

Production currently remains on the v5 provider-read profile, so all three mail capabilities remain PILOT/unexposed.

## Microsoft authorization boundary

The current directory-read Microsoft application returned HTTP 403 for Graph `/messages`, confirming that it does not possess mailbox-read authority.

The dedicated mail-read application must use Exchange Online Application RBAC with a custom resource scope. Entra Graph `Mail.Read` must not be added because Entra and Exchange grants are additive and an unscoped Entra grant would defeat the intended mailbox restriction.

Prepared operator artifact:

- `Setup-Jason-MailRead.ps1` — creates/validates the dedicated Entra app and service principal, uploads the public certificate, registers the service principal in Exchange, creates the exact pilot mailbox scope, assigns `Application Mail.Read`, and verifies positive/negative scope behavior.

Future helper tracked as `TODO-CONN-014`:

- `Add-Jason-Mailbox.ps1 -Mailbox user@teamaot.com` to add additional approved mailboxes without recreating the app/certificate/service principal.

## Blocking item

`SUPPORT-CONN-018` remains open.

Remaining external setup:

1. run the prepared Microsoft setup script from an authenticated Microsoft administrator session;
2. obtain the Application (client) ID and Service Principal Object ID;
3. provision the separate OpenBao `microsoft_graph.mail_read` certificate secret/AppRole;
4. persist the validated `microsoft_graph_mail` client boundary;
5. configure the exact approved mailbox allowlist;
6. activate provider-read v6;
7. prove approved mailbox search/read and attachment metadata;
8. prove a non-approved mailbox is denied;
9. verify `direct_provider_access=false`;
10. then run the procurement email correlation acceptance test.

## Grafana / roadmap state

Canonical roadmap milestones:

- `PROCURE-001` — **active** — Governed procurement and PO lifecycle;
- `MAIL-READ-001` — **blocked** — Scoped Microsoft mailbox evidence for procurement;
- `MAILBOX-HELPER-001` — **planned** — Approved mailbox onboarding helper.

The Jason Command Center includes dedicated Procurement Lifecycle and Procurement Mail Read stat panels in addition to the generic roadmap table.

## Section Goal closure criteria

Do not mark this Section Goal complete until:

- the dedicated Microsoft mail-read application and Exchange RBAC scope are live;
- approved mailbox positive/negative authorization is proven;
- one controlled vendor ETA/shipping message correlates to a controlled PO;
- Teams approval or the approved replacement approval path binds the exact proposed PO change;
- the PO/customer/inventory split survives receiving and ticket billing;
- the final controlled `2 ordered / 1 billed / 1 inventory` acceptance passes with authoritative readback;
- Grafana and documentation reflect the terminal result.
