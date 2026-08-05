# INF-001 — Secret Provider Foundation

**Status:** Foundation
**Owner:** Jason Architecture Authority
**Review interval:** Quarterly and before every provider-backed pilot
**Retirement criteria:** Replaced only by an approved provider-neutral secret service with equivalent or stronger controls

## Purpose

INF-001 defines the operationally complete secret-provider foundation required by every Jason capability that consumes external credentials.

A capability may request a logical secret name, but it may not ask an operator to discover or invent the provider implementation, executable path, service location, storage path, authentication method, or recovery procedure during execution.

## Failure that prompted this control

CAP-001 reached a live-read configuration prompt that requested an "approved secret command path" even though no canonical deployment record identified that command. The architecture described a provider-neutral boundary, and the bootstrap runbook named OpenBao as the pilot default, but the repository did not contain the concrete deployment facts needed by the operator.

That is a documentation and readiness failure. The correct response is to stop the dependent capability, record the gap, and complete INF-001 before any live provider access.

## Architectural contract

Capabilities request stable logical names such as:

```text
autotask.readonly
it_glue.readonly
datto_rmm.readonly
```

Only the Secrets Broker and its configured provider adapter may translate a logical name into a provider-specific reference.

The canonical operator command is:

```text
jason-secret <logical-secret-name>
```

The command must:

- accept one logical Jason secret name;
- execute without a shell expansion layer;
- return only the requested secret payload to the authorized process;
- never print provider tokens, root material, unseal material, or unrelated fields;
- emit redacted errors;
- fail closed;
- record access metadata without secret values.

The command is not considered available merely because an OpenBao service, container, backup unit, or configuration fragment exists.

## Required deployment record

Every Jason environment must maintain a canonical deployment record containing concrete, verified values for:

- environment name and profile;
- selected provider;
- provider runtime type: system service, container, managed service, or other approved form;
- service or container name;
- listener or endpoint;
- TLS mode;
- executable or wrapper path;
- configuration paths;
- storage path or backend;
- authentication method;
- logical-name mapping location;
- audit-device status;
- seal status and approved unseal method;
- backup service, schedule, destination, and last verified restore;
- health-check command;
- secret-resolution test command;
- owner and escalation contact;
- last verified timestamp and verifier;
- known exceptions and expiration dates.

Unknown values must be recorded as `UNVERIFIED` or `NOT IMPLEMENTED`. They must never be replaced by operator guesswork.

## Readiness gate

A provider-dependent capability must be denied before live execution unless all of the following are true:

1. The deployment record exists.
2. Required fields are populated with verified values.
3. The canonical wrapper path is documented and executable.
4. The wrapper passes a no-value health test.
5. The logical secret mapping exists.
6. Provider authentication is configured.
7. Audit logging is enabled or an approved time-bounded exception exists.
8. Backup and restore evidence is current for self-hosted providers.
9. The dependent capability references logical secret names only.
10. The operator runbook gives exact commands and does not contain discovery prompts.

## Operator experience rule

Jason commands and runbooks must not ask an operator for infrastructure facts that Jason owns and should already know.

Disallowed prompts include:

- "Approved secret command path"
- "Where is OpenBao installed?"
- "Is it running in Docker or systemd?"
- "What vault path should this capability use?"

When a required fact is absent, the command must identify the missing deployment-record field and stop.

## Initial implementation sequence

1. Create and verify the environment deployment record.
2. Identify the existing OpenBao runtime from approved installation evidence.
3. Implement `/usr/local/bin/jason-secret` or document another approved canonical path.
4. Configure logical-name mappings.
5. Add health, contract, redaction, and failure tests.
6. Update the bootstrap runbook with exact installation and recovery commands.
7. Add an automated documentation-readiness check.
8. Resume CAP-001 only after the INF-001 readiness gate passes.

## Definition of Done

INF-001 is complete when:

- the provider-neutral contract is implemented;
- one real provider adapter passes contract tests;
- the environment deployment record contains verified concrete values;
- the canonical `jason-secret` command is installed and tested;
- backup and restore evidence exists for a self-hosted provider;
- operator commands require no infrastructure discovery;
- dependent capabilities fail closed when the deployment record is absent or incomplete;
- documentation readiness tests enforce these requirements.
