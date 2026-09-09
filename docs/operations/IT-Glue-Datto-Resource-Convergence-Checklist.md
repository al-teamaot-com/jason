# IT Glue + Datto RMM Resource Convergence Checklist

## Goal

Prove the first read-only cross-provider Jason resource-convergence slice using the verified production IT Glue and Datto RMM connector boundaries while preserving the accepted managed-device authority model.

The bounded questions are now intentionally separate:

> Does Datto RMM establish one authoritative RMM-managed device observation?

and, independently:

> Does this IT Glue configuration safely represent that Datto-managed device?

IT Glue documentation quality is not a prerequisite for recognizing a device that is actively managed in Datto RMM.

## Proven prerequisites

As of 2026-08-10:

- `it_glue.readonly` resolves through the canonical JKD-003 provider-specific AppRole lifecycle;
- the dedicated Jason IT Glue key passed bounded governed live reads;
- `datto_rmm.readonly` resolves through the canonical JKD-003 provider-specific AppRole lifecycle;
- Datto OAuth and bounded live device reads passed;
- neither provider path persists runtime OpenBao tokens, OAuth bearer tokens, or raw provider payloads;
- both connectors emit `connector.requested` and `connector.completed` audit events;
- the project-local `.venv` is the canonical host validation Python environment;
- ADR-004 is accepted and establishes Datto RMM as the authoritative external provider for RMM-managed device existence and operational identity.

Credential provisioning is therefore not part of this convergence slice.

## Authority invariant

For RMM-managed devices:

1. Datto RMM is authoritative for managed-device existence, stable Datto external UID, and governed operational identity/state attributes.
2. IT Glue is a documentation observation and cannot independently establish or override managed-device operational identity.
3. Jason remains authoritative for provider-independent canonical Asset/Device identity and cross-provider mapping/promotion decisions.
4. A valid Datto observation remains valid even if no IT Glue mapping can be corroborated.
5. Relationship direction does not define source authority. J-118 canonical semantics remain `IT Glue configuration -> represents -> Datto managed-device observation`.

## Convergence invariant

The convergence service:

1. authorizes both reads through the provider-neutral resource registry;
2. translates generic resource requests into existing connector capabilities;
3. preserves one organization, principal, client, and correlation context across independent provider reads;
4. denies cross-organization correlation;
5. limits the first Datto candidate search to exactly one returned candidate for the positive proof;
6. establishes managed-device authority only from one unambiguous governed Datto observation;
7. creates INF-012 relationship evidence only when explicitly selected identity attributes agree;
8. performs no provider-to-provider communication;
9. performs no mutation;
10. does not persist raw provider payloads;
11. does not automatically create a Jason canonical device or promote provider evidence to canonical truth.

## First controlled live authority proof

Use one deliberately narrow Datto search hint.

1. execute one bounded Datto device search through `datto_rmm.device.search` with `max=1`;
2. require exactly one device candidate;
3. normalize only approved identity attributes observed in the response;
4. require a stable Datto external device UID;
5. mark the observation `datto_rmm:managed-device-authority`;
6. call the governed managed-device authority decision path;
7. retain only sanitized identity metadata and audit/status evidence;
8. perform no provider mutation and no canonical promotion.

This proof succeeds independently of IT Glue.

## Optional IT Glue documentation relationship proof

Once the Datto authority observation exists, evaluate one controlled IT Glue configuration.

1. select one IT Glue configuration ID belonging to the active organization context;
2. execute the configuration GET through `it_glue.entity.get`;
3. use the same bounded Datto device search and organization context;
4. normalize only identity attributes actually observed in the provider responses;
5. compare only explicitly approved attributes such as serial number, hostname, name, or another stable approved identifier;
6. create `ProviderRelationshipEvidence` only when every selected matching attribute is present and equal after normalization;
7. store the canonical relationship as `IT Glue configuration -> represents -> Datto managed-device observation`;
8. keep the relationship at `corroborated` or lower unless a separate governed verification threshold is satisfied;
9. retain only sanitized evidence metadata and provider-neutral references;
10. do not persist provider response bodies.

If matching attributes are missing or inconsistent, the documentation relationship remains `unresolved`. That is not a failure of the Datto device-authority proof.

## 2026-08-10 live result

The first physical Jason host proof established:

- one bounded Datto managed-device observation;
- authoritative provider: `datto_rmm`;
- authority scope: `rmm_managed_device_identity_and_operational_state`;
- stable Datto external device UID was present;
- approved Datto identity metadata included hostname;
- both IT Glue and Datto connector audit events were emitted;
- no canonical object was created;
- no canonical relationship was promoted;
- no provider mutation was performed;
- no raw provider payload or credential was printed or persisted.

The selected IT Glue configuration exposed a serial number, but the selected bounded Datto response did not expose a matching serial-number attribute. Jason therefore returned documentation relationship status `unresolved` with the reason that the requested matching attribute was absent or inconsistent. The Datto authority observation remained valid.

## Relationship semantics

A successful documentation correlation is evidence that an IT Glue configuration `represents` a Datto RMM managed-device observation. It does not merge the records, transfer provider authority, grant execution authority, or make the Datto provider UID the Jason canonical object ID.

Relationship evidence must preserve:

- source provider/resource ID;
- target provider/resource ID;
- organization boundary;
- matched attribute names, not raw protected values in repository evidence;
- confidence;
- verification state;
- observation time;
- source authority/provenance.

## Stop conditions

Stop or remain unresolved if:

- provider runtime secret verification fails;
- a Datto search is ambiguous or cannot be constrained to one candidate for the authority proof;
- the selected IT Glue configuration is outside the active organization context;
- provider response shape requires guessing identity fields;
- selected documentation-matching attributes are absent or inconsistent;
- raw secrets or provider payloads would need to be printed or committed;
- a mutation or provider-to-provider call would be required;
- a relationship would cross organization boundaries.

Do not broaden provider enumeration merely to force a documentation match.

## Validation and known regression-baseline issue

The PR #136 managed-device authority/convergence scope passes its focused test suite and GitHub Actions release gates. A broader connector-suite run on the Jason host exposed unrelated pre-existing stale/brittle tests and package-boundary problems. Those are tracked in issue #137 and must be repaired before the live Teams approval round-trip. They do not weaken or bypass this convergence proof.

## Next steps after first proof

1. preserve the Datto managed-device authority rule as policy by resource domain and attribute;
2. improve governed documentation reconciliation when provider response shapes expose sufficient stable identity evidence;
3. add provider-conflict reporting when IT Glue documentation and Datto operational identity disagree;
4. add bounded relationship traversal through the Central Orchestrator;
5. persist governed relationships behind the INF-012 provider-neutral repository interface only after explicit policy-controlled promotion;
6. restore a clean repository-wide connector regression baseline under issue #137 before the Teams live approval proof;
7. extend the same authority-by-domain approach deliberately to Autotask, Microsoft, and security-provider resources rather than assuming one global source of truth.
