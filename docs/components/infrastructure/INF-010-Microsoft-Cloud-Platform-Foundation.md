# INF-010 Microsoft Cloud Platform Foundation

## Purpose

INF-010 establishes Microsoft 365 and Azure/Entra services as a first-class governed provider family for Jason.

The platform foundation is intentionally broader than a single Microsoft Graph connector. It provides a shared identity, tenant, permission-profile, endpoint, metadata-discovery, and request-policy layer for capabilities that use Microsoft cloud services.

## Existing foundation reused

Jason already contains Microsoft onboarding and certificate-token foundations including:

- Microsoft administrator-consent request and callback validation;
- provider-independent client-boundary records;
- Microsoft onboarding orchestration;
- certificate credential contracts;
- MSAL-backed application-token acquisition;
- tenant-isolated token caching;
- safe Microsoft error translation.

INF-010 extends those foundations rather than replacing them.

## Microsoft service families

The canonical service catalog includes:

| Service | Initial provider | Primary surface | Foundation mode |
|---|---|---|---|
| Microsoft Graph | `microsoft_graph` | Graph v1.0 | governed |
| Entra ID | `microsoft_entra` | Graph v1.0 | governed |
| Exchange Online | `microsoft_exchange_online` | Exchange/Graph | governed |
| SharePoint Online | `microsoft_sharepoint_online` | Graph v1.0 | governed |
| OneDrive | `microsoft_onedrive` | Graph v1.0 | governed |
| Teams | `microsoft_teams` | Graph v1.0 | governed |
| Intune | `microsoft_intune` | Graph v1.0 | governed |
| Defender | `microsoft_defender` | Graph initially; product APIs may be separate providers | governed |
| Purview | `microsoft_purview` | Graph initially | observe/read |
| Service Health | `microsoft_service_health` | Graph v1.0 | observe/read |
| Licensing | `microsoft_licensing` | Graph v1.0 | governed |

A capability selects the service family it needs. Agents do not select arbitrary endpoints directly.

## Metadata-driven resource discovery

Microsoft cloud integration must not grow as a collection of hard-coded business questions, fixed entity workflows, or one-off Graph paths.

For Microsoft Graph, Jason's preferred read architecture is provider-metadata driven:

1. the Microsoft provider adapter obtains the authoritative Graph OData CSDL metadata document through a governed provider path;
2. the adapter parses entity sets, entity types, inherited structural properties, and declared keys into a bounded provider-neutral resource catalog;
3. Jason converts those structural resources into opaque open-world resource handles;
4. the primary reasoning layer selects only opaque resources and structural fields that are present in that catalog;
5. Jason revalidates the selected resource, fields, selectors, operators, tenant boundary, permission profile, and read mode before compiling a provider request;
6. the provider adapter performs the protocol-specific Graph request and returns bounded evidence to the Central Orchestrator.

The entity-set name and request path are therefore learned from provider-published metadata rather than being encoded per client, per question, or per Microsoft business object.

A newly published structural entity set can become discoverable without adding an entity-specific Jason capability, provided it satisfies the governed metadata, permission, lifecycle, and authority gates. New provider data does **not** automatically create new authority.

### Model/request separation

The reasoning layer must never be permitted to manufacture a Graph URL, raw OData expression, arbitrary query option, tenant ID, credential, permission, or provider resource handle.

The model-visible catalog contains Jason-generated opaque resource handles plus bounded structural field descriptions. The underlying provider resource handle remains trusted orchestration state. Structured filters are compiled by the provider adapter from validated field/operator/value tuples, with literal escaping and fixed bounds.

Navigation relationships are intentionally excluded from the initial metadata-derived read surface because following them can materially widen evidence scope. They may be introduced later through separately governed relationship discovery.

### Generic execution seam

Metadata-derived resources use provider-neutral generic read/search operation classes rather than one capability name per Graph entity. This keeps the Central Orchestrator and open-world query planner independent of Microsoft entity names while allowing the Microsoft adapter to own Graph protocol details.

Existing fixed Microsoft helper functions may remain for backward compatibility or narrow platform functions, but they are not the pattern for expanding Jason's general Microsoft information-reading ability.

## Permission profiles

Permission profiles are policy data. They are deliberately narrower than the total permissions an application might technically be able to request.

Initial profiles include:

- `directory-read`
- `identity-investigation-read`
- `mail-investigation-read`
- `device-compliance-read`
- `security-investigation-read`
- `collaboration-permissions-read`

All initial profiles are read-only. A future write-capable profile requires separate governance, documentation, tests, approval classes, and production evidence.

Metadata discovery does not infer or grant permissions. Microsoft resource metadata describes what exists; Jason's approved permission profile and the tenant's actual consent describe what may be read. A discovered resource that is not authorized must fail closed.

## Request policy

`MicrosoftCloudRequest` describes a provider request before execution.

The foundation enforces:

1. registered service family;
2. registered permission profile;
3. profile-to-service authorization;
4. safe request path construction;
5. allowlisted query-option construction;
6. read-mode method restrictions;
7. provider-supported operation mode;
8. bounded selectors, projections, filters, ordering, and result limits;
9. canonical public-cloud base endpoints.

The request builder returns a governed request description. It does not itself create authority.

## Architectural rules

### Identity first

Every Microsoft call must be bound to an approved Jason client boundary and Microsoft tenant identity before a token is acquired.

### Least privilege by profile

Capabilities request named permission profiles, not arbitrary permission strings.

### Provider family, not capability coupling

Capabilities such as mail investigation or identity investigation consume governed Microsoft providers through the orchestrator. They must not embed Microsoft credentials, tenant mappings, or direct provider-to-provider calls.

### Discover structure; do not hard-code questions

Jason should determine how to answer an information request by reasoning over the resources and fields that the governed provider currently exposes. Business workflows such as "find a user's email" are not implemented as fixed Microsoft request chains when the same result can be planned from provider-discovered resources and cross-provider evidence.

### Read before write

The first production Microsoft milestone is read-only. Write operations must be introduced as separate governed increments.

### No token exposure

Access tokens, certificates, private keys, refresh material, and Microsoft diagnostic payloads that may contain protected information must not enter normal evidence or logs.

## Planned information domains

The Microsoft platform is intended to make governed Microsoft information available for reasoning across domains including:

- Microsoft 365 users and directory objects;
- Entra identity and access evidence;
- mailbox and mail-flow evidence;
- account-compromise evidence;
- Microsoft 365 offboarding evidence;
- tenant security-posture evidence;
- licensing evidence;
- Teams membership and configuration evidence;
- SharePoint and OneDrive permission evidence;
- Intune device-compliance evidence;
- Defender incident evidence;
- Microsoft service-health evidence.

These are desired information domains, not instructions to create hard-coded query workflows.

## Source-side metadata-driven read foundation

The current source branch adds the following non-production foundation:

- bounded Microsoft Graph CSDL resource/schema discovery;
- a provider-neutral discovered-resource catalog contract shared across provider types;
- an opaque bridge from provider-discovered resources into Jason's open-world planner;
- a generic metadata-backed Graph read compiler with explicit projections and structured filters;
- fail-closed validation of unknown resources, fields, methods, query options, and unsafe paths;
- preservation of existing capability-backed open-world resource handles;
- tests proving that a synthetic new provider entity can become discoverable without entity-specific production code.

This work intentionally does not add Microsoft entity names to the existing IT Glue/Autotask provider-capability map or provider-read argument adapter.

## Deployment prerequisites

Before live deployment Jason still requires:

1. verified OpenBao-backed Microsoft certificate credential resolution for the runtime path;
2. an AOT-owned Microsoft application registration with the approved read-only permission set;
3. documented permission-profile-to-consent mapping;
4. durable client-boundary and Microsoft tenant onboarding state;
5. a controlled tenant for live acceptance;
6. live metadata and token validation without token display;
7. provider-resource execution wiring through the Central Orchestrator and Jason authority boundary;
8. bounded live read acceptance proving tenant isolation, evidence shaping, and zero write authority;
9. tenant offboarding/cache-invalidation validation;
10. operational evidence and deployment records;
11. explicit approval before any production activation, runtime/MCP recreation, authority grant, or tenant consent change.

## Current status

**Foundation built; metadata-driven read expansion is source-only and not deployed.**

No Microsoft production permission, tenant consent, credential, authority grant, MCP surface change, live API request, runtime recreation, or write capability is introduced by the current source-only work. Production Microsoft reads remain unavailable until the prerequisites above are proven and separately approved.
