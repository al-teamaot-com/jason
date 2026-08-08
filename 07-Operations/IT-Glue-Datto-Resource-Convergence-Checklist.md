# IT Glue + Datto RMM Resource Convergence Checklist

## Goal

Prove the first read-only cross-provider Jason resource-convergence slice without creating provider-specific parallel architecture or exposing credentials.

The bounded question is:

> Which Datto RMM device corresponds to this IT Glue configuration, and what evidence supports that relationship?

## Repository foundation

The convergence layer now:

1. authorizes IT Glue and Datto RMM reads through the INF-011 resource registry;
2. translates generic resource requests into the existing connector capabilities;
3. preserves one organization, principal, client, and correlation context across independent provider reads;
4. denies cross-organization correlation;
5. creates INF-012 relationship evidence only when explicitly selected attributes agree;
6. keeps provider calls read-only;
7. performs no provider-to-provider communication;
8. does not persist raw provider payloads;
9. leaves large evidence behind the INF-013 reference boundary;
10. requires live payload normalization to be proven from bounded provider reads rather than guessed.

## Credential boundary

The repository is intentionally ready to stop before live provider access.

### IT Glue

Existing connector contract:

- logical secret: `it_glue.readonly`
- required credential field: `api_key`
- API base: `https://api.itglue.com`
- first bounded operation: one configuration GET through `it_glue.entity.get`

The API key must be read-only for the intended discovery scope and must be stored through the Jason secret-provider path rather than committed, pasted into code, or supplied through normal logs/evidence.

### Datto RMM

Existing connector contract:

- logical secret: `datto_rmm.readonly`
- required credential fields: `base_url`, `access_token`
- first bounded operation: one device search through `datto_rmm.device.search`

The current connector consumes a provider base URL and bearer access token. If the production Datto RMM credential source is an API key/secret or OAuth client rather than a durable bearer token, credential acquisition must be bound behind the secret/transport boundary before live validation. Do not commit or log token material.

## Preflight

Run:

```bash
python3 tools/resource_convergence_preflight.py
```

Expected properties:

- `status` = `credential_boundary_reached`
- `network_contacted` = `false`
- `secret_resolved` = `false`
- both logical-secret contracts are listed
- the two bounded provider reads are listed

## First live validation after credentials exist

Use one controlled client/organization and one known configuration/device pair.

1. resolve `it_glue.readonly` through the approved Jason secret provider;
2. execute one exact IT Glue configuration GET;
3. resolve `datto_rmm.readonly` through the approved Jason secret provider;
4. execute one bounded Datto RMM device search;
5. capture only sanitized response-shape metadata and candidate identity fields;
6. finalize normalization for stable identity attributes such as provider IDs, device/configuration names, serial numbers, and other verified identifiers actually returned by the APIs;
7. evaluate candidate relationship evidence through the convergence service;
8. keep the relationship at inferred/corroborated status unless the evidence threshold for verification is satisfied;
9. record the occurrence through J-119 only if it is a material provider-neutral business event;
10. keep raw provider payloads outside normal chat, Git, logs, and repository evidence.

## Stop conditions

Stop before or during live validation if:

- either logical secret cannot be resolved through the approved secret provider;
- provider credentials have broader write authority than required and cannot be constrained;
- organization/client scope cannot be established exactly;
- the IT Glue configuration belongs to a different organization than the active context;
- the Datto RMM device search cannot be bounded to the intended client/device context;
- response shape differs from the expected provider contract and would require guessing;
- raw secrets or protected payloads would be printed or committed;
- a mutation or provider-to-provider call would be required.

## Additional providers

RocketCyber, SaaS Alerts, VulScan, Graphus, BullPhish, ID Agent, and Microsoft remain queued behind this first convergence proof. Their credential contracts should be introduced only when their verified APIs and first bounded read operations are ready for controlled validation.
