# Autotask dynamic schema read engine — proposed v13

**Source only. Not activated or deployed. Standing production freeze active.**

## Why

We should not develop a new function for every Autotask REST entity.
`service.entity.search` and `service.entity.read` already form one
governed query/read interface. The active source previously hardcoded
five generic read entities in v11 and another seventeen dormant v12
entities. This change replaces that expanding name list with a dynamic
provider metadata check, under an explicit new source-bound profile.

The October 27 metadata inventory listed 230 vendor entity names.
Only 84 had live schema observations: 62 `canQuery=true` with API user
query access `All`, 20 `None`, and two `Restricted`; the remaining
146 were not verified. Metadata is not proof of successful record reads.

## One dynamic query mechanism

The proposed activation profile is
`itglue-autotask-entra-dynamic-schema-read-catalog-v13`.

1. Jason's existing Central Orchestrator validates authenticated
   requester identity, JKD-001 authority, and read-only capability.
2. The adapter compiles a bounded entity name and canonical field
   filters into Autotask's documented GET `/V1.0/<Entity>/query`.
   Supported structured operators include `eq`, `noteq`, comparisons,
   `contains`, `beginsWith`, `endsWith`, existence, and list inclusion.
   Untrusted raw provider JSON and arbitrary URLs cannot be supplied.
3. Every dynamic read checks this exact API account's live
   `entityInformation`: `canQuery` must be true and
   `userAccessForQuery` must be `All`. A separate live fields
   description must prove `id` and every filter field queryable.
   Missing, ambiguous, restricted, or denied metadata blocks record
   retrieval. No cached permission grant is used.
4. Optional `select` compiles Datto's native `IncludeFields` and
   the connector strips unexpected fields if the API ignores selection.
5. Read requests are bounded to 1–500 records; existing API pagination
   follows same-origin continuation URLs within hard limits. The caller
   can continue by `after_resource_id`, with API-record ID ascending.
6. Jason's **separate information-release authorization** still
   decides what the requester can view. The v13 dynamic path requires
   an authenticated AOT human, an unbound customer client, Jason-managed
   mode, and observe-only capability.

Example generic search selectors:

```json
{
  "entity": "ActionTypes",
  "filters": {"name": {"op": "contains", "value": "Service"}},
  "select": ["name"],
  "page_size": 100
}
```

The exact read equivalent uses
`service.entity.read` with `entity` and `resource_id`.
There are no ActionTypes-specific or TaxRegions-specific functions.

Existing specialized attachment, labor, charge, and ticket-note
access paths remain separately governed and cannot be bypassed through
the generic route. Entities where the API reports `Mine`,
`Restricted` or `None` are not presumed globally readable.
This does not add provider write operations or broader customer
disclosure permissions.

## Status and completion conditions

The configuration file still selects **v11**, not v13. This is an
explicit source-only, dormant profile that leaves v10 production and
the owner promotion freeze intact. It is not correct to claim that
all 230 vendor entity names are queryable until the actual API user
permissions, field metadata, real record reads, pagination, and negative
disclosure tests have been independently verified.

Before deployment: protected CI, full native change/parallel-work
review, an immutable v13 candidate and rollback profile, fresh native
preproduction, exact-SHA owner approval, and actual connected MCP
count/page/exact-ID/Projects plus representative v13 dynamic reads.
The existing owner freeze and controlled write permissions remain.

Official provider references:
- https://psa.datto.com/help/DeveloperHelp/Content/APIs/REST/API_Calls/REST_Basic_Query_Calls.htm
- https://psa.datto.com/help/DeveloperHelp/Content/APIs/REST/API_Calls/REST_Advanced_Query_Features.htm
