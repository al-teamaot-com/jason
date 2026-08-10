# Project Jason — IT Glue + Datto Host Operational Proof — 2026-08-10

## Scope

This record captures the first physical Jason-host operational validation of the canonical OpenBao provider runtime, governed IT Glue and Datto RMM live reads, bounded provider discovery, the Datto managed-device authority decision, and the documentation gaps discovered during the session.

No secret values, RoleIDs, SecretIDs, OpenBao tokens, provider credentials, OAuth bearer tokens, or raw provider payloads are recorded here.

## Repository and host starting point

The Jason repository was confirmed at:

`/home/al/projects/jason`

The work began from current `main`, then moved to PR #136 branch:

`feature/operational-live-proof-runbook`

All host commands explicitly entered the repository and printed the current folder, branch/revision, and organized PASS/FAIL sections before validation.

## OpenBao host preflight

Verified on the physical Jason host:

- OpenBao is hosted in Docker rather than as an active systemd OpenBao service.
- The host listener is loopback-only at `127.0.0.1:8200` through Docker proxying.
- OpenBao version observed: `2.6.1`.
- OpenBao was initialized, unsealed, and active/non-standby.
- `/usr/local/bin/jason-secret` exists and is executable.
- Provider AppRole bootstrap directories existed for IT Glue and Datto RMM under `/opt/jason/bootstrap/secrets/openbao/`.
- Protected RoleID and SecretID files were present; their values were never displayed.

## Historical `jason-secret` ambiguity discovered

The historical/general wrapper health and contract commands returned:

`DENIED: OpenBao token file is not configured.`

This initially appeared to suggest the OpenBao provider runtime was broken even though the production architecture had already moved to provider-specific AppRole authentication.

The session established and documented the canonical distinction:

- `jason-secret` token-file health/contract behavior is a historical commissioning/general wrapper boundary;
- production provider runtime authentication uses provider-specific OpenBao AppRoles through JKD-003;
- production provider readiness must not be determined by creating or restoring a persistent token merely to make the historical wrapper pass;
- production AppRole login produces a short-lived token, reads the one allow-listed provider secret, and revokes the temporary token;
- shared persistent provider runtime tokens remain prohibited.

This finding required updates to the bootstrap/secrets runbook and the canonical secret-provider deployment record so the same ambiguity is not rediscovered in a future session.

## Project-local Python environment discovered as required

System Python was Python 3.12.3 but did not contain `pytest`.

A repository-local `.venv` was created and initialized from `implementation[dev]`. The resulting environment provided Python 3.12.3 and pytest 9.1.1 plus the Jason connector development dependencies.

The canonical host validation rule is now:

- use `~/projects/jason/.venv` for host development/validation;
- do not assume system Python contains Jason test dependencies;
- document the exact bootstrap in the operational runbook.

## Direct resolver contract correction

An initial direct live AppRole proof failed because `OpenBaoSecretResolver.resolve()` was invoked without the required `ConnectorContext`.

The actual contract requires:

- logical secret name;
- governed `ConnectorContext` with a non-empty correlation ID and active capability/organization context.

After correcting the validation harness, live AppRole resolution succeeded for both providers without printing secret values.

## INF-001 / production AppRole readiness proven

The following passed:

- canonical AppRole resolver tests;
- provider secret architecture tests;
- IT Glue credential-safe provider-secret preflight;
- Datto RMM credential-safe provider-secret preflight;
- live AppRole authentication for `it_glue.readonly`;
- live AppRole authentication for `datto_rmm.readonly`;
- approved secret-field contract validation;
- temporary OpenBao service-token self-revocation;
- secret-value suppression.

This established the canonical production provider secret runtime as operational on the Jason host.

## First governed IT Glue live read

A bounded IT Glue live read passed:

- capability: `it_glue.entity.query`;
- entity: Organizations;
- maximum records: 1;
- provider network contacted only during explicit live mode;
- connector audit events: `connector.requested`, `connector.completed`;
- raw provider payload not persisted or printed;
- provider credential values not printed.

## First governed Datto RMM live read

A bounded Datto RMM live read passed:

- capability: `datto_rmm.device.search`;
- maximum records: 1;
- runtime provider credentials used only for the governed read;
- Datto OAuth access token not persisted;
- connector audit events: `connector.requested`, `connector.completed`;
- raw provider payload not persisted or printed.

## Safe provider discovery added

The initial operational tooling did not provide a documented operator path for selecting a safe convergence test object. Rather than requiring source introspection or manual provider hunting, PR #136 added bounded sanitized discovery tools:

- `tools/it_glue_configuration_discovery.py`
- `tools/datto_rmm_device_discovery.py`

Both perform credential-safe preflight, remain read-only, bound the result to one record for the positive proof, use provider AppRole runtime authentication, and print only approved identity metadata needed for the proof.

## Controlled test observations

The bounded IT Glue discovery returned one controlled configuration with a stable external configuration ID plus approved name and serial-number metadata.

A bounded Datto search using the IT Glue serial-number hint returned one Datto device observation with a stable external device UID and hostname metadata, but the returned bounded Datto shape did not expose a serial-number field suitable for corroborating that IT Glue configuration.

The raw provider records are intentionally not copied into this repository record.

## ADR-004 — Datto RMM managed-device authority

During the convergence work, the physical AOT workflow was formalized as an architecture decision:

- Datto RMM is the authoritative external provider for RMM-managed device existence and operational identity/state;
- IT Glue is a documentation observation for device-related records;
- Jason remains authoritative for provider-independent canonical Asset/Device identity and cross-provider mapping/promotion decisions.

The first implementation used an inverse relationship name `represented_by`. Focused tests correctly rejected that value because J-118's canonical vocabulary already defines `represents`.

The implementation and documentation were corrected to preserve the canonical relationship:

`IT Glue configuration -> represents -> Datto managed-device observation`

Provider authority and relationship direction are now explicitly documented as separate concepts. ADR-004 rejects adding an inverse canonical synonym merely to place Datto on the source side.

## Live managed-device authority proof

The final live authority proof passed under the accepted ADR-004 model:

- authoritative provider: Datto RMM;
- authority scope: RMM-managed device identity and operational state;
- exactly one bounded Datto device observation accepted;
- stable external Datto device identifier present;
- approved operational identity metadata present;
- Datto and IT Glue connector audit events emitted;
- canonical Jason object created: false;
- canonical relationship promoted: false;
- provider mutation performed: false;
- raw provider payload persisted: false;
- raw provider payload printed: false.

The IT Glue documentation relationship remained `unresolved` because the requested serial-number attribute was absent or inconsistent across the two governed observations. This was treated correctly as a documentation-reconciliation condition rather than a failure of Datto managed-device authority.

## Test and release validation

The focused PR #136 managed-device authority/convergence test scope passed.

GitHub Actions for the finalized branch passed:

- `Validate Jason`;
- `Validate IT Glue Datto Resource Convergence`.

A broader host connector-suite run exposed unrelated pre-existing baseline defects. Those were not hidden or waived. They are tracked in issue #137 and include:

- stale Microsoft bounded-automation expected error text;
- dependency-sensitive Microsoft JWKS test JWT fixtures rejected by current PyJWT before mocked verification paths;
- relationship-registry test use of `__dict__` on a `slots=True` dataclass;
- Teams approval delivery tests using a stale `ApprovalRequest(summary=...)` constructor;
- package-layout collection problems for artifact-evidence and AWS provider tests under the declared implementation package configuration.

The Teams approval baseline defects are explicitly blocking before the planned live Teams approval round-trip.

## Documentation corrected during this session

PR #136 now updates or adds the following operational/architecture documentation so the morning's work is not dependent on chat history:

- `05-ADR/ADR-004-Datto-RMM-Managed-Device-Authority.md`;
- `07-Operations/OPS-ITGLUE-DATTO-LIVE-CONVERGENCE-PROOF.md`;
- `07-Operations/Jason-Bootstrap-and-Secrets-Runbook.md`;
- `07-Operations/Jason-Secret-Provider-Deployment-Record.md`;
- `07-Operations/IT-Glue-Datto-Resource-Convergence-Checklist.md`;
- this host-proof session record;
- `08-Session-Records/CURRENT.md` resume checkpoint.

PR #136 also contains the bounded discovery and live authority-proof tools used by those runbooks.

## Security invariants preserved

Throughout the session:

- agents did not communicate directly with other agents;
- provider reads were routed through governed connector/orchestration boundaries;
- provider AppRole identities remained provider-specific;
- secrets were passed by protected runtime reference rather than copied between components;
- no provider-to-provider communication occurred;
- no provider mutation occurred;
- no canonical relationship was silently promoted;
- no raw provider payload was committed as evidence;
- no secret, OpenBao token, RoleID, SecretID, OAuth bearer token, API key, or password was exposed in repository documentation.

## Next operational gate

Before the first live Teams approval round-trip:

1. resolve issue #137 and restore the canonical repository-wide connector regression baseline;
2. specifically repair/validate the Teams approval delivery tests against the current `ApprovalRequest` contract;
3. run release validation through the normal branch -> tests -> release validation -> PR -> governance review -> merge workflow;
4. only after the Teams approval boundary is green perform the live approval delivery/ingress round-trip.
