# IT Glue + Datto RMM Resource Convergence Checklist

## Goal

Prove the first read-only cross-provider Jason resource-convergence slice without creating provider-specific parallel architecture or exposing credentials.

The bounded question is:

> Which Datto RMM device corresponds to this IT Glue configuration, and what evidence supports that relationship?

## Repository foundation

The convergence layer now:

1. authorizes IT Glue and Datto RMM reads through the INF-011 resource registry;
2. translates generic resource requests into existing connector capabilities;
3. preserves one organization, principal, client, and correlation context across independent provider reads;
4. denies cross-organization correlation;
5. creates INF-012 relationship evidence only when explicitly selected attributes agree;
6. keeps provider calls read-only;
7. performs no provider-to-provider communication;
8. does not persist raw provider payloads;
9. leaves large evidence behind the INF-013 reference boundary;
10. requires live payload normalization to be proven from bounded provider reads rather than guessed.

## Credential boundary

### IT Glue

- logical secret: `it_glue.readonly`
- durable field: `api_key`
- API base: `https://api.itglue.com`
- first bounded operation: one configuration GET through `it_glue.entity.get`

The key must be dedicated to Jason and constrained to the least privilege available for this read-only discovery slice. Password access is not required. The value belongs only in the approved Jason/OpenBao secret boundary.

### Datto RMM

- logical secret: `datto_rmm.readonly`
- durable fields: `api_url`, `api_key`, `api_secret`
- runtime-only material: `access_token`
- first bounded operation: one device search through `datto_rmm.device.search`

Jason must not persist a Datto bearer token as the durable secret. The connector exchanges the durable API credentials for a bearer token at runtime and uses that token only for the bounded provider request. Token material must not enter Git, chat, normal logs, repository evidence, or the durable OpenBao secret record.

Use the most restrictive Datto API security/component level available for the dedicated Jason API identity. If read-only scope cannot be established with confidence, stop before live validation.

## OpenBao provisioning readiness

Before credentials exist, it is safe to prepare logical paths and policy bindings, but do not create placeholder secret values that could be mistaken for production credentials.

Expected durable secret shapes:

```text
it_glue.readonly
  api_key

datto_rmm.readonly
  api_url
  api_key
  api_secret
```

Provisioning tooling must:

- accept values without terminal echo;
- avoid placing values on command lines or in shell history;
- write directly through the approved OpenBao path;
- clear transient variables after the write;
- report only field presence and PASS/FAIL state;
- never print secret values during verification.

## Preflight

Run:

```bash
python3 tools/resource_convergence_preflight.py
```

Expected properties:

- `status` = `credential_boundary_reached`
- `network_contacted` = `false`
- `secret_resolved` = `false`
- IT Glue requires `api_key`
- Datto requires durable `api_url`, `api_key`, and `api_secret`
- Datto `access_token` is identified as runtime-only and non-persistent
- the two bounded provider reads are listed

## First live validation after credentials exist

Use one controlled client/organization and one known configuration/device pair.

1. resolve `it_glue.readonly` through the approved Jason secret provider;
2. execute one exact IT Glue configuration GET;
3. resolve durable `datto_rmm.readonly` through the approved Jason secret provider;
4. acquire a Datto bearer token at runtime behind the connector boundary;
5. execute one bounded Datto RMM device search;
6. capture only sanitized response-shape metadata and candidate identity fields;
7. finalize normalization for stable identity attributes actually returned by the APIs;
8. evaluate candidate relationship evidence through the convergence service;
9. keep the relationship inferred/corroborated unless the verification threshold is satisfied;
10. record a J-119 event only for a material provider-neutral occurrence;
11. keep raw provider payloads outside normal chat, Git, logs, and repository evidence.

## Stop conditions

Stop before or during live validation if:

- either logical secret cannot be resolved through the approved secret provider;
- provider credentials have broader authority than required and cannot be constrained;
- organization/client scope cannot be established exactly;
- the IT Glue configuration belongs to a different organization than the active context;
- the Datto RMM device search cannot be bounded to the intended client/device context;
- token acquisition or response shape differs from the verified provider contract and would require guessing;
- raw secrets or protected payloads would be printed or committed;
- a mutation or provider-to-provider call would be required.

## Credential lifecycle

Dedicated Jason provider credentials must have an owner, creation date, review interval, and revocation/rotation procedure. Rotation must replace the durable OpenBao values without requiring workflow changes. Revocation must fail closed and must not cause Jason to fall back to personal, shared, cached, or embedded credentials.

## Additional providers

RocketCyber, SaaS Alerts, VulScan, Graphus, BullPhish, ID Agent, and Microsoft remain queued behind this first convergence proof. Their credential contracts should be introduced only when their verified APIs and first bounded read operations are ready for controlled validation.
