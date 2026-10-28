# Autotask governed read routing and failure classification

This release improves capability discovery and diagnostics. It does not grant additional Autotask permissions or silently retry denied reads.

- The canonical `service.entity.search` and `service.entity.read` routes may be offered as candidate alternatives to named contract, inventory, purchase-order and invoice reads. Each selection is made explicitly and evaluated independently through normal requester authorization, provider metadata and field-level query verification.
- A missing client context is an authorization failure, **not** evidence that the provider lacks data. Do not attempt another route to evade it.
- Invalid canonical selectors are returned as `INVALID_CAPABILITY_ARGUMENTS` without forwarding exception text. Correct filters to a field-to-value mapping (for example `{"resourceID": 29682927}`) before retrying.
- Provider HTTP failures are separate from selector and authorization failures. A provider-level `userAccessForQuery=None` must not be treated as connector coverage that can be worked around.
- Specialized time-entry, notes, charges and attachment routes continue to enforce their own contracts and disclosure controls.

Acceptance: select an authorized candidate only after checking its actual provider capability and requester authorization; verify live reads, exact IDs and pagination. No automatic fallback on denial, no provider writes, and no changes to production without native release approval.
