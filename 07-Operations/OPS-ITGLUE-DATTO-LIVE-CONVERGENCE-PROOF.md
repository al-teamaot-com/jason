# OPS — IT Glue + Datto RMM Live Convergence Proof

## Purpose

This runbook defines the controlled host-side proof that Jason can perform two governed live provider reads and produce provider-neutral cross-provider relationship evidence without bypassing organization isolation, secret-provider boundaries, connector audit, capability controls, or canonical-promotion policy.

The proof is deliberately observe-only. A successful run does **not** promote the relationship into canonical truth and does not grant identity, approval, capability, provider, or execution authority.

## Required backend state

Before using this runbook, `main` must contain the validated implementations for:

- governed IT Glue live-read boundary;
- governed IT Glue + Datto RMM live convergence service;
- IT Glue and Datto RMM convergence projectors;
- operator-facing operational convergence command;
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
4. The logical secrets required by the governed connectors resolve through their provider AppRoles:
   - `it_glue.readonly`
   - `datto_rmm.readonly`
5. No secret values are echoed, copied into shell history, written into source files, or stored in test evidence.
6. The operator has a valid Jason organization identifier for the client being tested.
7. A harmless known IT Glue configuration is selected through the bounded discovery procedure below or by an already-known non-secret identifier.
8. A bounded Datto RMM search hint is selected that should resolve to exactly one known device.
9. At least one explicit matching attribute is known, preferably serial number. Hostname/name matching may be used for the first proof only when the test objects are known to be unique.

If any prerequisite cannot be proven, stop. Do not widen the search or guess provider mappings.

## Safe IT Glue configuration discovery

Operators must not reverse-engineer internal class names or dump raw IT Glue responses to locate a test configuration. Use the supported bounded discovery tool.

Credential-safe preflight:

```bash
cd ~/projects/jason
.venv/bin/python tools/it_glue_configuration_discovery.py
```

The preflight must report `network_contacted: false`, `maximum_records: 1`, and `entity: Configurations`.

A live discovery remains GET-only, is bounded to one returned configuration, uses the production IT Glue AppRole resolver, and prints only the configuration external ID plus approved identity attributes (`name`, `hostname`, `serial_number`) when present. Raw provider payloads and credentials are not printed or persisted.

When a known IT Glue organization ID is available, constrain discovery with `--organization-id`. When a known configuration name is available, also constrain with `--name`.

```bash
sudo env PYTHONPATH=/home/al/projects/jason/implementation \
/home/al/projects/jason/.venv/bin/python \
tools/it_glue_configuration_discovery.py \
  --live-read \
  --organization-id '<KNOWN_IT_GLUE_ORGANIZATION_ID>' \
  --name '<KNOWN_CONFIGURATION_NAME>'
```

Do not put secret values in these arguments. If no safe organization/name constraint is available, the tool still limits the provider response to one record; the operator must verify the candidate is appropriate before using it for convergence.

The supported bounded IT Glue read implementation is `ItGlueLiveReadService` with `ItGlueLiveReadRequest`. Operator runbooks should reference supported tools/services and must not invent or infer implementation class names.

## Safe test-object requirements

The selected IT Glue configuration and Datto RMM device must belong to the same Jason organization/client boundary. The test must not use production mutation capabilities.

The Datto candidate limit remains `1` for the first proof. If the search cannot resolve one unambiguous candidate, the proof fails closed and a better search hint must be selected.

Use the identity attributes emitted by bounded IT Glue discovery to form the Datto search hint. Prefer a stable serial number when Datto search supports the value reliably; otherwise use a unique hostname/name. Do not broaden to unbounded inventory enumeration merely to find a match.

## Preflight evidence to record

Record non-secret evidence for:

- UTC timestamp;
- Jason host identifier;
- deployed Git commit SHA;
- Jason organization ID;
- operator/principal ID;
- correlation ID generated for the proof;
- selected IT Glue configuration ID;
- bounded Datto search hint description, avoiding sensitive data where possible;
- explicit matching attribute names;
- confirmation that `it_glue.readonly` resolved through the provider-specific AppRole boundary;
- confirmation that `datto_rmm.readonly` resolved through the provider-specific AppRole boundary;
- connector registration for `it_glue` and `datto_rmm`;
- capability registration for `it_glue.entity.get` and `datto_rmm.device.search`.

Record only presence/readiness of secrets, never secret material.

## Positive proof

Construct the governed IT Glue and Datto RMM connectors using the approved runtime configuration and secret provider. Construct `OperationalConvergenceRunner` with exactly those connectors.

Invoke one `OperationalConvergenceCommand` with:

- exact Jason organization ID;
- explicit operator/principal ID;
- unique correlation ID;
- known IT Glue configuration ID;
- bounded Datto RMM search hint;
- explicit `matched_attributes` tuple;
- confidence value justified by the selected attributes;
- candidate limit `1`.

Expected execution sequence:

1. Jason authorizes the IT Glue resource query.
2. Jason executes `it_glue.entity.get` through the governed IT Glue connector.
3. Jason authorizes the Datto RMM resource query.
4. Jason executes `datto_rmm.device.search` through the governed Datto connector.
5. Provider results are verified against the planned providers.
6. Provider projectors normalize both results into organization-bound `IdentityEvidence`.
7. The matching attributes are compared exactly after normalization.
8. Jason returns `ProviderRelationshipEvidence` with canonical relationship `represents` and verification state `corroborated`.
9. No canonical relationship is created by this command.

## Required positive assertions

The proof passes only when all of the following are true:

- both provider reads completed through governed connectors;
- both results were bound to the expected Jason organization;
- the IT Glue external ID matches the selected configuration;
- exactly one Datto device candidate was projected;
- each requested matching attribute exists on both normalized observations and matches exactly after normalization;
- relationship evidence references the expected IT Glue configuration and Datto device;
- relationship evidence source authority records governed provider reads;
- relationship evidence remains evidence-only and has not been inserted into the canonical relationship registry;
- connector audit events exist for both provider operations;
- no secrets appear in console output, logs, artifacts, or committed files.

## Negative / fail-closed proof cases

Run the following negative tests without changing provider data.

### Wrong organization context

Repeat with a deliberately incorrect Jason organization identifier or mismatched connector context. Expected result: operation denied before relationship evidence is produced.

### Ambiguous Datto search

Use a search hint known to return multiple candidates while allowing a candidate limit greater than one only for this negative test. Expected result: the Datto projector rejects the ambiguous result and no relationship evidence is produced.

### Non-matching attribute

Request an attribute known not to match. Expected result: relationship evidence construction fails closed.

### Missing matching attribute

Request an attribute absent from one observation. Expected result: relationship evidence construction fails closed.

### Wrong provider/capability projection

Exercise the deterministic test path or controlled fixture rather than altering production routing. Expected result: the projector rejects the unexpected provider/capability pair.

### Missing secret

Only if it can be tested safely without disrupting other Jason workloads, temporarily use a deliberately invalid logical-secret mapping in an isolated test configuration. Expected result: connector execution fails before provider contact. Do not delete production secrets for this test.

## Evidence handling

The final proof package should be stored through INF-013 artifact/evidence storage once the host-side evidence writer is available. Until then, retain only sanitized non-secret proof data needed to establish:

- what was tested;
- who/what identity initiated it;
- which organization was in scope;
- which Git revision and configuration version were used;
- which provider objects were observed;
- what exact attributes corroborated the relationship;
- what negative tests were performed;
- whether each invariant passed.

Large provider responses should not be copied into tickets, chat, or repository documentation. Store artifacts centrally and pass immutable references.

## Success criteria

The operational milestone `IT Glue + Datto RMM live convergence proven` may be recorded only after:

1. the positive proof passes;
2. tenant-mismatch, ambiguous-result, and attribute-mismatch negative tests fail closed as designed;
3. connector audit evidence exists;
4. no secret leakage is detected;
5. the deployed Git SHA and proof correlation ID are recorded;
6. evidence is stored or queued for INF-013 immutable storage;
7. the operator confirms that no canonical promotion or provider mutation occurred.

## After the proof

Do not immediately enable automated canonical promotion or side-effecting actions because the live observation succeeded. The next governed step is to use this proven observe path as an input to explicit policy-controlled promotion and, separately, to a low-risk Central-Orchestrator action workflow requiring its own authorization and approval gates.
