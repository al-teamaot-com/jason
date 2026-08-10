# OPS — IT Glue + Datto RMM Live Convergence Proof

## Purpose

This runbook defines the controlled host-side proof that Jason can recognize an RMM-managed device from Datto RMM as the authoritative external managed-device observation, then independently evaluate whether an IT Glue configuration represents that device.

The proof is deliberately observe-only. It does **not** create a Jason canonical Asset/Device object, promote a provider mapping into canonical truth, or grant identity, approval, capability, provider, or execution authority.

The governing architecture decision is `ADR-004-Datto-RMM-Managed-Device-Authority.md`.

## Authority model

For the RMM-managed device domain:

- **Datto RMM is authoritative for managed-device existence and operational provider identity.** This includes the Datto device UID and governed runtime identity/state attributes exposed by the RMM platform.
- **IT Glue is a documentation observation.** An IT Glue configuration may represent a Datto-managed device, but IT Glue does not independently establish or override the managed device's operational identity.
- **Jason remains authoritative for canonical provider-independent object identity and cross-provider mappings.** A Datto UID is an external mapping identifier, not a Jason canonical object ID.

A missing, stale, or unmatched IT Glue configuration must therefore leave the documentation relationship unresolved without erasing or downgrading the valid Datto managed-device authority observation.

When corroborated, the canonical J-118 relationship direction is:

`IT Glue configuration -> represents -> Datto managed-device observation`

Provider authority and relationship direction are separate concerns. Do not introduce or persist an inverse `represented_by` canonical relationship.

## Required backend state

Before using this runbook, the approved branch/revision must contain the validated implementations for:

- governed IT Glue live-read boundary;
- governed Datto RMM live-read boundary;
- provider-specific OpenBao AppRole runtime authentication;
- Datto managed-device authority policy;
- IT Glue and Datto convergence projectors;
- live convergence service and operator-facing convergence command;
- provider-neutral relationship evidence and tenant isolation.

The operator must record the exact Git commit deployed to the Jason host.

## Canonical host bootstrap

Host validation is performed from the Jason repository with a project-local Python virtual environment. Do not assume `pytest` or Jason development dependencies are installed in system Python.

```bash
cd ~/projects/jason
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e './implementation[dev]'
.venv/bin/python --version
.venv/bin/python -m pytest --version
```

Reusing an existing `.venv` is permitted when it was built from the current checkout and remains healthy.

The full host bootstrap and secret-runtime distinction are maintained in `07-Operations/Jason-Bootstrap-and-Secrets-Runbook.md` and `07-Operations/Jason-Secret-Provider-Deployment-Record.md`.

## Canonical provider secret runtime

Production IT Glue and Datto RMM reads use provider-specific OpenBao AppRole runtime authentication. They do **not** depend on a persistent shared provider token file.

Expected bootstrap paths are:

- `/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/role-id`
- `/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/secret-id`
- `/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/role-id`
- `/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/secret-id`

The production resolver logs in through AppRole, obtains a short-lived service token, performs the allow-listed KV v2 read, and revokes the temporary token. Provider runtime tokens must not be persisted.

### Important historical `jason-secret` distinction

`jason-secret --health` and `jason-secret --contract-test` exercise the historical/general token-file contract and can return:

`DENIED: OpenBao token file is not configured.`

That result does **not** by itself prove that the production provider AppRole runtime is unhealthy. Do not create, copy, expose, or broaden a persistent provider token merely to make the historical wrapper health check pass. Validate production provider readiness through the canonical AppRole resolver and provider-specific bootstrap identities.

Direct `OpenBaoSecretResolver.resolve()` validation requires both the governed logical name and a `ConnectorContext` containing a non-empty correlation ID. Validation output must report only success/failure and approved field names; it must never print resolved values, RoleIDs, SecretIDs, OpenBao tokens, or provider credentials.

## Host prerequisites

The Jason host must satisfy all of the following before convergence provider contact:

1. The repository checkout is clean and on the approved revision/branch for the proof.
2. The project `.venv` is healthy and contains the current Jason implementation plus development dependencies.
3. OpenBao is reachable locally, initialized, unsealed, and using the approved provider-specific AppRole boundary.
4. `it_glue.readonly` and `datto_rmm.readonly` resolve through their provider AppRoles.
5. No secret values are echoed, copied into shell history, written into source files, or stored in test evidence.
6. The operator has a valid Jason organization identifier for the client being tested.
7. A bounded Datto observation resolves to exactly one device before managed-device authority is accepted.
8. Any candidate IT Glue configuration is treated as documentation until the relationship is corroborated.
9. Relationship matching uses explicit governed attributes such as serial number, hostname, name, or another approved identity attribute available on both observations.

If any prerequisite cannot be proven, stop. Do not widen the search or guess provider mappings.

## Safe provider discovery

### IT Glue configuration discovery

Use the supported bounded discovery tool rather than dumping provider payloads or introspecting implementation internals.

```bash
cd ~/projects/jason
.venv/bin/python tools/it_glue_configuration_discovery.py
```

A live discovery is GET-only, bounded to one configuration, AppRole-backed, and prints only the external configuration ID plus approved identity attributes when present.

### Datto RMM device discovery

Use the supported bounded Datto discovery tool:

```bash
cd ~/projects/jason
.venv/bin/python tools/datto_rmm_device_discovery.py --search '<NON_SECRET_SEARCH_HINT>'
```

A live discovery is GET-only, bounded to `max=1`, AppRole-backed, and prints only approved identity attributes and the stable Datto external device UID. Raw provider payloads, provider credentials, bearer tokens, and AppRole material are not printed or persisted.

An ambiguous Datto result is not authoritative. Improve the bounded search hint rather than widening inventory enumeration.

## Credential-safe preflight

Every live proof tool must support a no-network preflight before provider contact. The preflight must disclose only non-secret execution intent such as provider, capability, maximum record count, whether filters/search are supplied, and whether network contact or provider credentials will be used.

A preflight must not resolve or print provider secret values.

## Positive authority proof

The first success condition is independent of IT Glue.

Jason passes the managed-device authority proof when:

1. a governed bounded Datto read returns exactly one device;
2. the Datto projection contains a stable external device identifier;
3. the projection is organization-bound;
4. the projection is explicitly marked `datto_rmm:managed-device-authority`;
5. `establish_managed_device_authority()` accepts the observation;
6. no provider mutation, canonical object creation, or canonical mapping promotion occurs.

At this point Jason has evidence that the RMM-managed device exists even if IT Glue documentation is absent or unresolved.

The supported operator proof utility is:

`tools/managed_device_authority_live_proof.py`

It must be run first in credential-safe preflight mode and then in explicit live-read mode only after the preflight is accepted.

## Documentation relationship proof

When evaluating an IT Glue configuration, `OperationalConvergenceRunner` performs governed provider reads and returns both:

- a `managed_device_authority` decision for the Datto observation; and
- optional `relationship_evidence` for the IT Glue documentation mapping.

Expected execution sequence:

1. Jason executes the approved bounded IT Glue configuration read.
2. Jason executes the approved bounded Datto device read.
3. Provider results are verified against planned providers and organization context.
4. The Datto projector marks the device observation with managed-device authority.
5. Jason accepts the Datto authority observation independently of IT Glue matching.
6. The IT Glue projector marks its configuration as a documentation observation.
7. Jason compares only the explicitly requested governed matching attributes.
8. If the attributes corroborate, Jason returns `IT Glue configuration -> represents -> Datto managed-device observation` relationship evidence with status `corroborated`.
9. If the attributes are absent or inconsistent, Jason returns relationship status `unresolved`, no relationship evidence, and preserves the Datto managed-device authority decision.
10. No canonical relationship is created by this command.

## Required positive assertions

The authority portion passes only when:

- the Datto provider read completed through the governed connector;
- exactly one Datto device candidate was projected;
- the device is bound to the expected Jason organization;
- its source authority is `datto_rmm:managed-device-authority`;
- managed-device authority remains independent from IT Glue relationship state;
- no secrets or raw provider payloads are printed or persisted.

The documentation relationship portion is `corroborated` only when:

- the IT Glue observation is bound to the same organization;
- each requested matching attribute exists on both observations and matches after normalization;
- relationship evidence points from IT Glue documentation to the Datto managed-device observation using canonical `represents`;
- relationship evidence remains evidence-only and has not been promoted into the canonical relationship registry.

An `unresolved` documentation relationship is an acceptable and expected outcome when the Datto device is valid but the IT Glue record cannot be safely linked.

## 2026-08-10 completed host proof

The first physical-host proof completed successfully and is recorded at:

`08-Session-Records/IT-Glue-Datto-Host-Operational-Proof-2026-08-10.md`

The proof established:

- canonical provider-specific AppRole resolution for IT Glue and Datto RMM;
- bounded governed live reads for both providers;
- bounded sanitized discovery paths;
- one valid Datto managed-device authority observation;
- connector audit events for both providers;
- no persistent provider runtime token;
- no canonical object creation;
- no canonical relationship promotion;
- no provider mutation;
- no raw provider payload or secret material printed or persisted.

The selected IT Glue documentation relationship remained `unresolved` because the requested serial-number attribute was absent or inconsistent across the governed observations. The Datto authority observation remained valid as designed.

## Negative / fail-closed proof cases

### Wrong organization context

A cross-organization provider observation or mapping must be denied. No relationship evidence is produced.

### Ambiguous Datto search

A Datto search that produces more than one device must fail closed. Managed-device authority is not established from an ambiguous result.

### Non-matching or missing documentation attribute

The IT Glue relationship becomes `unresolved` and no relationship evidence is created. The already-valid Datto managed-device authority observation remains intact.

### Wrong provider/capability projection

A provider/capability mismatch is denied before authority or relationship evidence is accepted.

### IT Glue attempts to establish managed-device authority

A non-Datto provider observation must be rejected by the managed-device authority policy.

### Missing secret

Use only isolated test configuration if this can be exercised safely. Production provider secrets must never be deleted or modified for a negative test.

## Evidence handling

The final proof package should be stored through INF-013 artifact/evidence storage once the host-side evidence writer is available. Until then, retain only sanitized non-secret proof data needed to establish:

- what was tested;
- who or what identity initiated it;
- which organization was in scope;
- which Git revision and configuration version were used;
- which Datto managed device was observed;
- whether an IT Glue relationship was corroborated or unresolved;
- which exact attributes were evaluated;
- what negative tests were performed;
- whether each invariant passed.

Large provider responses should not be copied into tickets, chat, or repository documentation. Store artifacts centrally and pass immutable references.

## Validation baseline note

The focused authority/convergence test scope and GitHub release gates passed for PR #136. A broader host connector-suite run exposed unrelated pre-existing test and package-boundary defects. Those are tracked in issue #137 and must be resolved before the live Teams approval round-trip.

Do not weaken fail-closed production behavior to make stale tests pass, and do not treat issue #137 as permission to bypass the clean release gate for future Teams approval work.

## Success criteria

The operational milestone distinguishes two outcomes:

**Datto managed-device authority proven** when the bounded Datto authority proof passes.

**IT Glue documentation relationship corroborated** only when the optional cross-provider relationship proof also passes.

A valid Datto managed device with unresolved IT Glue documentation is not a failed device-authority proof. It is a documentation reconciliation condition that must remain visible and must not be silently promoted.

## After the proof

Do not immediately enable automated canonical promotion or side-effecting actions because an observation succeeded. The next governed workstream is issue #137: restore a clean repository-wide connector regression baseline, especially the Teams approval delivery boundary, then perform the first live Teams approval round-trip under the normal branch -> tests -> release validation -> PR -> governance review -> merge workflow.
