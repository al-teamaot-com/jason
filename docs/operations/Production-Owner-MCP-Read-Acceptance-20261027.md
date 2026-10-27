# Required external Autotask owner-read canary — source-only proposal

**P0. Not deployed. No release approval or production freeze exception.**

## Why

The previous v11 release passed HTTP health, native preproduction, CCC,
full manifest and Release Manager closure, but authenticated ChatGPT
Autotask ticket reads failed information release. A real connected read
must now be a mandatory acceptance gate when the immutable Autotask
read profile changes.

## Bounded evidence flow

After native preflight and before a production mutation, Release Manager
creates a fresh, SHA-bound, expiring owner canary intent (mode 0600) in a
shared AOT-only state directory. Only a successful, normally authorized
MCP read from an authenticated and governed AOT human Entra/Jason
identity (`person-entra-<object-id>` or an active legacy `person-al`
binding) in the `aot` organization, with **no customer client binding**,
is eligible
to produce a metadata-only witness.

The MCP witness contains no customer names, ticket descriptions, email,
notes, project content or credentials. It records a unique session ID,
candidate revision, approved read profile, observed time, read operation
and a bounded ticket count/IDs. A service-only, simulated health canary,
denial, user-bound client request, unknown source profile, expired intent
or legacy release cannot produce an accepted witness.

Before independently closing and committing a new last-known-good
revision, the Production Manager must verify ALL four real user
operations against one consistent search scope:

1. Real `service.ticket.count`, with positive count not exceeding 100.
2. `service.ticket.search` for that scope, 50-item first page and
   exact cursor continuation as needed, with total IDs equal to count.
3. `service.ticket.read` for an ID actually returned in the first page.
4. The newly activated `service.entity.search` for Projects, bounded
   to one result (zero results is valid after successful authorization).

If any proof is missing before the 240-second limit, native promotion
fails inside its existing rollback transaction. The rollback target,
profile, root previous-LKG and container-health fixes are independently
reviewed in #2083. Protected CCC, drift and root write authority remain
unchanged. No response data is disclosed by this witness.

## Operational acceptance procedure

During a future **separately owner-approved exact-SHA** promotion, the
connected owner/authorized operator must execute genuine MCP reads
through the installed Jason connector while the native PM waits.
Use a narrow real ticket-created window containing between 1 and 100
tickets, e.g. a previously measured 72-ticket 24-hour window; request
count, ordered 50-record pages, one exact ticket, and one Projects
generic search. Do not use direct Autotask provider API or synthetic
service requests. The immutable production candidate must not be
reported "complete" until this **independent live requester gate**
and the existing CCC/drift/host rollback checks pass.

This stage does **not** determine the exact root cause of the previous
intermittent or release-specific requester denial. It prevents the
same failure from being accepted as a healthy release again.

## Parallel source integration

PR #2074 adds an optional `verify_release_ticket_read_canary` MCP tool after
`execute_read_capability`. This P0 gate instead records the source-bound
receipt inside `execute_read_capability` itself, immediately before successful
return. The two insertion points are separate and do not conflict; neither
delegates requester disclosure authority to a service canary. The remaining
integration requirement is a source-bound end-to-end proof after both merge.

The complete count, pages, exact read and Projects probe must all be from
**the same authenticated AOT human**; a session cannot combine unrelated
staff identities. Owner approval of the release is still a separate,
mandatory exact-SHA authority gate. The witness never grants new reads.

2026-10-27 binding evidence: The active connected Microsoft/Jason identity
store exposes JIT-enrolled AOT principals using the `person-entra-` family.
Hard-coding the historical release approver `person-al` would make the
acceptance witness impossible to satisfy even if every authorized provider
read succeeded. The writer now accepts only that already-authenticated AOT
human family and the previous trusted alias, with tenant and customer
binding restrictions unchanged.
