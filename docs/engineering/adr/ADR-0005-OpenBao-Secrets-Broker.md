# ADR-0005: Use OpenBao-Backed Logical Secret Resolution

**Status:** Accepted
**Decision date:** 2026-08-03

## Context

Provider credentials must not be embedded in source code, interface configuration, logs, or agent context. Automated services require least-privilege access to only their assigned credentials.

## Decision

Use OpenBao as Jason's governed secret store and resolve credentials through logical secret names.

Each provider identity receives:

- a dedicated OpenBao policy;
- a dedicated AppRole;
- root-only bootstrap credentials;
- short-lived service tokens;
- access only to its approved secret path;
- permission to revoke only its own temporary token.

Agents do not access OpenBao directly.

## Consequences

Provider code remains independent of secret values and storage details.

Provisioning, rotation, backup, and recovery procedures become operational requirements.
