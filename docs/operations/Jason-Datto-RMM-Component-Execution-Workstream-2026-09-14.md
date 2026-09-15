# Jason Datto RMM Component Execution Workstream — 2026-09-14

## Current status

The governed Datto RMM component-execution workstream is active on isolated branch `feature/jason-datto-component-execution-20260914`, based on the accepted production documentation head `13941dfb97abd3f0ed2268ad1daed37fa61e00ec`.

Production runtime remains read-only. No execution capability has been activated in production and no Datto component or quick job has been executed by this workstream.

Phase 3 received explicit owner approval. The owner created a separate Datto execution API identity with the intended provider-side containment. Jason has now successfully staged that identity in OpenBao, repaired and proven the execution AppRole token lifecycle, authenticated to Datto with the execution identity, and proven that the identity does not carry Global Settings View authority.

The successful harmless provider proof established:

- `datto_rmm.execution` is usable as a separate provider credential;
- its OpenBao AppRole has a five-minute service-token TTL, no default policy, execution-only ACL access, and the approved two-use token lifecycle;
- the dedicated ACL permits only execution-secret read plus explicit token self-revocation;
- one execution-secret read followed by `revoke-self` succeeds;
- the revoked token is unusable afterward;
- Datto OAuth authentication succeeds;
- `GET /api/v2/system/status` succeeds with HTTP 200;
- account, account-devices, and account-components reads that require Global Settings View are denied with HTTP 403;
- no Datto mutation request occurred;
- no provider response body or bearer token was persisted or printed;
- OpenBao, MCP, and runtime containers remained unchanged and running.

The successful provider-proof record is maintained at `docs/operations/Jason-Datto-RMM-Execution-Identity-Harmless-Provider-Proof-2026-09-15.md`. The preceding staging/recovery history is retained in the related 2026-09-15 operational records.

A subsequent GET-only Device Visibility probe resolved two valid devices through the existing read identity, but both the site and device reads returned HTTP 403 through the execution identity. That result is intentionally recorded as inconclusive rather than treated as a visibility failure, because Datto requires separate Devices View permission for the device GET while the execution identity is designed around the minimum quick-job permission set. The same observability problem applies to API Component Level because account component enumeration additionally requires Global Settings View, which the execution identity intentionally lacks.

The evidence strategy has therefore been tightened: do not broaden the execution identity merely to make proof endpoints observable. Provider-side Device Visibility and API Component Level configuration is sufficient to continue source-only implementation work, while independent end-to-end enforcement remains deferred to the first separately approved live pilot quick job. This decision is recorded at `docs/operations/Jason-Datto-RMM-Phase3-Evidence-Strategy-2026-09-15.md`.

Draft PR #184 tracks this isolated workstream. Issue #183 tracks the capability objective.

## Phase 1 — read-only automation foundation — complete in source/tests

The first source-only milestone includes:

- canonical read-only capability `automation.component.search`;
- provider-neutral `automation.job.read`;
- a Datto automation-read connector using the existing `datto_rmm.readonly` logical credential;
- account component catalog reads through `GET /api/v2/account/components`;
- bounded complete component pagination before canonical filtering;
- exact job status reads through `GET /api/v2/job/{jobUid}`;
- fail-closed durable-identity checks for components and jobs;
- bounded canonical result projection that does not return arbitrary provider fields;
- omission of component variable default values from the released read model;
- provider-neutral Integration Broker resources for automation components and jobs;
- Central Orchestrator runtime routing for only the two read-only automation capabilities;
- explicit absence of `automation.component.execute` from the activated capability/provider/invoker surface.

Focused Datto read-foundation CI passed at source head `5c528972410fdd5a737081043f3db7da6b1ba73a` in GitHub Actions run `34867883313`.

## Phase 2 — governed proposal / exact-request foundation — complete in source/tests

Phase 2 remains non-production and does not contain a live Datto mutation executor. It adds deterministic source-only construction of the exact future quick-job request behind the existing proposal/approval boundary.

Implemented controls include:

- durable component allowlist entries with canonical component identity, human-readable name, provider implementation identity, allowed endpoint classes, variable policy, optional provider metadata fingerprint, approval policy, and active/suspended/retired state;
- component-variable policies with supported bounded types (`string`, `boolean`, `date`, `selection`), required variables, maximum lengths, and selection allowlists;
- exact component/provider identity matching;
- optional provider metadata-fingerprint pinning to fail closed on implementation drift;
- exact target device-class restriction;
- rejection of arbitrary or unknown variables, including arbitrary command/script fields that are not part of the allowlist contract;
- deterministic Datto quick-job request construction for `PUT /api/v2/device/{deviceUid}/quickjob`;
- deterministic provider-request digest binding without releasing the raw provider request as user-facing proposal data;
- human-readable reason included in the mutation-plan digest so approval cannot be reused after the purpose changes;
- explicit governed client scope required for component proposals;
- generic mutation controls retained for execute mode: idempotency key plus exact, expiring approval bound to capability/principal/organization/client/argument digest;
- proposal audit evidence retained;
- live execution still terminates at the intentional fail-closed boundary: `Datto RMM live mutation executor is not configured.`

Tests prove that a valid exact approval can reach only that disabled live-execution boundary, and that changing the reason or component variables after approval invalidates the approval digest.

The focused `Validate Datto RMM Automation Foundation` workflow passed at source head `e4afc7afd1c465bee16891e356d59d902ecd3a84` in GitHub Actions run `34868375772`.

## Security boundary preserved

Neither phase converts the existing Datto read identity into an execution identity. Component execution is built around a separate least-privilege logical credential, `datto_rmm.execution`, and exact `EXECUTE` authority.

The existing `DattoRmmMutationConnector` is still proposal-only for live mutations. No quick-job provider mutation has been enabled in runtime composition, and no arbitrary PowerShell/shell/batch/script-text execution interface has been introduced.

## Phase 3 — provider identity / containment — complete enough to continue source-only implementation

Phase 3 controls are:

1. Use a separate Datto RMM API identity for Jason execution rather than broadening `datto_rmm.readonly`.
2. Apply only the minimum Security Level required for the quick-job operation.
3. Restrict Device Visibility to the intended pilot scope.
4. Assign an API Component Level containing only explicitly approved pilot component(s).
5. Store the execution credential separately as `datto_rmm.execution` under OpenBao rather than reusing the read credential.
6. Prove authentication and harmless access boundaries before any quick-job execution.
7. Keep the runtime write/execution surface disabled until a later explicit production-activation approval.

### Phase 3 completed evidence

The following are complete and proven:

- separate provider execution identity created;
- isolated OpenBao execution credential staged as version 1;
- execution AppRole separated from the read-only credential;
- CAS-required KV behavior handled fail-closed;
- live OpenBao ACL response shape (`data.policy`) handled and regression-tested;
- execution ACL limited to execution-secret read plus token self-revocation;
- execution AppRole restored to the approved two-use token lifecycle;
- explicit self-revocation and post-revoke denial proven;
- harmless Datto OAuth authentication proven;
- absence of Global Settings View authority proven with GET-only 403 responses;
- GET-only Device Visibility probe executed without mutation and correctly classified as inconclusive because the execution identity intentionally lacks the read permissions needed to isolate Device Visibility from permission denial;
- no component execution, provider mutation, runtime activation, or service restart occurred.

### Deferred end-to-end provider enforcement proof

Do not add Devices View or Global Settings View merely to make Device Visibility or API Component Level observable through GET-only proof endpoints. Datto applies Device Visibility and API Component Level to the quick-job operation itself, so the first separately approved low-risk pilot quick job is the appropriate end-to-end enforcement proof.

Until that separately approved pilot occurs, the owner-configured provider restrictions are configuration evidence, while independent runtime enforcement remains explicitly unproven.

## Next implementation step

Continue source-only implementation of the governed live mutation transport, runtime composition boundary, approval enforcement, audit capture, and job follow-up path. Keep production activation disabled.

When source/tests are ready, stop at the production activation / first-live-pilot approval boundary and present one bounded approval request rather than introducing additional exploratory proof loops.

## Approval boundary

Phase 3 provider identity/containment work is explicitly owner-approved.

Separate explicit approval is still required before deploying a runtime execution surface or running the first live component/quick job. The first live pilot remains intended to be one explicitly approved low-risk diagnostic/read-only component on one noncritical test endpoint with per-run approval and governed post-job verification.
