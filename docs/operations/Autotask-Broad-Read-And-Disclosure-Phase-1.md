# Autotask Read Coverage and Requester Disclosure — Phase 1

**Owner architecture decision:** October 27, 2026. Issue #2077. **No permission for new writes or unreviewed production deployments.**

## Goal

Jason's AOT-authorized provider identity may read and reason over records across the Autotask PSA environment. The **recipient** (technician, customer, Teams room, export or another MSP tenant) may receive only what its independently verified output authority permits. Read access, disclosure and write permission are separate decisions. A source code merge is not proof the new reads are available.

## New canonical read-only surface

The pre-existing, authenticated, audited `autotask.entity.query` connector is reused through `service.entity.search` and `service.entity.read`. No arbitrary HTTP paths, raw `search` JSON or mutation operations are exposed.

The first verified queryable **additional** families are: `Projects`, `Tasks`, `ServiceCalls`, `ProjectNotes`, and `TicketAdditionalConfigurationItems`. Existing rich reads for tickets, notes, attachments, companies, contacts, contracts, assets, products, invoices, quotes and purchasing stay unchanged.

- Bounded equality filters (at most 12 simple fields), maximum 500 records per call, exact source-backed durable IDs and `after_resource_id` pagination.
- Exact record read is a read-only ID query whose result must contain **exactly one matching ID**. A malformed, missing, ambiguous or wrong-ID result fails closed.
- The generic route deliberately **does not** bypass specialized TimeEntries requester checks, ticket attachment company validation, contract company-bound routes or sensitive content reads.
- Provider schema descriptions remain separate and may reveal API queryability where a verified query path is not yet available.

## Requester disclosure

Generic reads use the existing Autotask information-release authorizer. A trusted AOT organization identity with valid execution authority and a non-client-bound active Microsoft/Jason binding can receive non-sensitive cross-customer facts; sensitive contents remain derived-only / not raw-releasable. Customer-bound identities do not receive general cross-customer results, even though the provider's internal service-account fetch can succeed. A denied or missing requester authorization never becomes a blank authorization to disclose.

The same protection must hold for Teams, ChatGPT replies, attachments, generated reports, and downstream notifications. This increment reuses the existing centralized response release boundary; it **does not yet certify every downstream export/notification path**. Multi-MSP tenant boundaries remain strict.

Writes, updates, deletes, attachments uploads and notifications remain governed through existing separate write credentials, risk and exact-argument approvals.

## Activation and regression contract

The new capabilities are **PILOT** until the independent **v11** provider-read activation profile `itglue-autotask-entra-comprehensive-entity-read-catalog-v11` is selected in the governed runtime configuration. Profiles v1–v10 retain their original capability sets, including the current production v10; deploying code alone must not silently expand AOT provider scope.

Before activating v11, prove the managed runtime configuration and independent production health monitoring agree on the selected version. A mismatched exporter or incomplete service configuration is a release blocker, not a reason to disable the drift watchdog.

Minimum acceptance:
1. Provider-backed metadata proof for each additional queryable entity.
2. Isolated and authenticated positive AOT read, cross-client relationship traversal, exact record IDs, pagination and complete result semantics.
3. Negative customer-bound / untrusted requester disclosures, unsupported entity injection, raw REST query attempts, duplicate IDs and sensitive data redaction.
4. Existing ticket count/pagination/exact read and the PM independent CCC/rollback/timer checks.
5. Protected-main SHA-bound whole-release impact review, preproduction and Owner-authorized single controlled production release. Immediate native rollback if foundation regressions occur; retain all development worktrees and freezes except the exact one-off exception.

## Remaining coverage

The full **all-queryable-Autotask** goal is **NOT completed** by this first increment. Project attachments require content/metadata separation; TimeEntries remain on the explicit requester/company-verified route; administrative/UI-only records may not have public REST APIs; other entity types must be inventoried against provider entityInformation and fields before activation. Extend versioned capabilities without inventing provider support or weakening output controls.

**Status:** Source-only implementation and tests. Do not assert new `service.entity.search/read` are in the active MCP registry until v11 is installed and positively tested end to end.
