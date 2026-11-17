# AOT-MSA native Service Bundle membership: provider verified, source-only preflight

**Status:** Dormant, non-executing code proposal. No production activation, Owner authority, contract, invoice, price or provider mutation.

## Authoritative provider behavior

- Live Jason `service.entity.describe({entity:"ServiceBundleServices"})` confirmed create/query/delete supported, update unsupported, and native create/query permission reported All (November 17, 2026).
- Live Jason `service.entity.fields.describe` confirmed exact required keys `serviceBundleID` and `serviceID`; the provider marks these identifiers read-only in field metadata.
- Autotask official REST reference: https://autotask.net/help/DeveloperHelp/Content/APIs/REST/Entities/ServiceBundleServicesEntity.htm. Creating duplicate membership is rejected. Admin module permissions are required.
- The provider can **recalculate the bundle's extended price** when the native "Use sum of selected service unit prices" option is on. Even child membership writes can therefore be financially impactful.

## Current source-only component

`implementation/connectors/autotask/bundle_membership_plan.py` builds only an exact proposal for an inactive, zero-priced, new AOT-MSA Bundle. It does not import an HTTP transport, register a capability, change a provider record, grant authority or issue a signed approval. No bundle membership route is added to the active registry or to the existing four-operation scoped catalog release.

It rejects legacy Bundle IDs 1-4, active/incorrectly named bundles, nonzero prices, absent or price-recalculating native setting evidence, invalid Service/Bundle IDs, malformed or duplicate child links, wrong billing code, and missing evidence references.

## Follow-on operational prerequisites

1. Complete the separate four-operation Jason service-identity release under the exact protected and root-governed approval boundary. Do not merge this membership work into that pinned executable image.
2. Approve a specific inactive new AOT-MSA bundle and underlying Services, then create each under individually governed native actions and read back its exact ID.
3. Independently read the parent bundle's actual price setting and full child-link set; do not trust a caller-supplied assertion. Approve any price effect explicitly.
4. Release a distinct readback-bound `ServiceBundleServices` mutation capability after separate architecture/security tests and exact-scope authorization. Reuse Jason's dedicated API-only Autotask identity; human identity authorizes and is auditable.
5. For each approved membership link, require before-and-after native child query, no duplicate, exact ID matching, price readback, contract/invoice noninterference, immutable audit and no automatic repeat of an ambiguous POST.

**The provider-supported write route is not operational in Jason yet.** This preflight is executable only as pure local plan validation.
