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

The operator should record the exact Git commit deployed to the Jason host.

## Host prerequisites

The Jason host must satisfy all of the following before provider contact:

1. The repository checkout is clean and on the approved `main` revision.
2. The canonical `jason-secret` wrapper is installed and functioning.
3. OpenBao is reachable through the approved Jason secret-provider boundary.
4. The logical secrets required by the governed connectors exist and are readable by the Jason runtime identity:
   - `it_glue.readonly`
   - `datto_rmm.readonly`
5. No secret values are echoed, copied into shell history, written into source files, or stored in test evidence.
6. The operator has a valid Jason organization identifier for the client being tested.
7. A harmless known IT Glue configuration is selected.
8. A bounded Datto RMM search hint is selected that should resolve to exactly one known device.
9. At least one explicit matching attribute is known in advance, preferably a stable device attribute such as serial number. Hostname/name matching may be used for the first proof only when the test objects are already known to be unique.

If any prerequisite cannot be proven, stop. Do not widen the search or guess provider mappings.

## Safe test-object requirements

The selected IT Glue configuration and Datto RMM device must belong to the same Jason organization/client boundary. The test must not use production mutation capabilities.

The Datto candidate limit should remain `1` for the first proof. If the search cannot resolve one unambiguous candidate, the proof fails closed and a better search hint must be selected.

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
- confirmation that `it_glue.readonly` resolved through the approved secret boundary;
- confirmation that `datto_rmm.readonly` resolved through the approved secret boundary;
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