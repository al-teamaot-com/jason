# Autotask v11: Internal requester source authorization without Graph email dependency

**Status:** Source-only P0 correction. Owner's all-promotion freeze remains
active; not deployed, no read expansion active in production.

## Observed incident and architectural dependency

The Owner-approved 2026-10-27 v11 attempt passed native preproduction and
release certification, but real connected Jason `service.ticket.count`,
`service.ticket.search`, and new `service.entity.search` operations were
denied with `SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED`. We restored v10.

The existing `runtime_source_authorization_bindings_from_env` first resolves
an active, durable Microsoft/Jason tenant/object binding, then performs
**synchronous Microsoft Graph directory email enrichment**. A missing or
failed directory lookup returns no binding and therefore the source-read
authorization gate denies release—even for `jason_managed` Autotask
reads where no provider-native email impersonation is used.

The recorded incident does not conclusively prove which Graph/identity step
failed; it establishes that this dependency is a plausible denial source
and unnecessarily couples independent AOT internal reads to provider email
profile availability.

## Narrow, fail-closed correction

Only when the immutable active read profile is **exactly v11**,
the Autotask requester mode is `jason_managed`, the request is
**AOT-internal / no customer client**, and authenticated human
JKD-001 authority is positive, the Autotask information-release stage
may rely on the **active durable Microsoft/Jason binding itself**.

This positive proof additionally requires matching Jason principal,
active binding status, and unscoped binding `client_id=None`. That
removes an unrelated live **email** dependency; it is not uncredentialed
read access and **does not grant provider permissions**.

Customer-bound or non-AOT callers, disabled/ambiguous/unbound
principals, missing authority context, service principals, wrong
permission modes, or unknown prior profiles remain fail-closed.
The native `impersonated` Autotask connector, labor and attachment
special cases, IT Glue provider ACL decisions, and native Microsoft
Graph operations **continue to require directory-enriched bindings**.
Sensitive information still receives derived-output-only handling.

## Security and acceptance limitation

This makes one intentional tradeoff: an internal AOT human with an
**already valid** Microsoft-authenticated Jason session and active durable
binding no longer requires a fresh Graph profile lookup for each
Autotask service-account read. Session authentication, JKD-001, tenant,
client-scope and disclosure restrictions remain mandatory; central
identity revocation must still disable the durable binding and/or
terminate the authenticated session. No customer-bound read benefits
from the fallback.

Unit tests simulate a real SQLite trusted binding with a Graph
email lookup failure, plus missing, inactive, mismatched, client-bound,
service and invalid authority cases. These **do not prove live production
success**. Before any future production promotion, both authenticated
ticket count/pages/exact-ID and generic Projects must pass the native
post-deployment owner/operator acceptance gate, under the new SHA,
with exact rollback prevalidated.

This change cannot be deployed without a separate new exact-SHA
Owner exception to the standing all-production-promotion freeze.
