# ADR-007 — MCP Operational Return Path Boundary

**Status:** Accepted  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-09-21

## Context

Jason exposes governed operational capabilities to ChatGPT through the Jason MCP service. During support and development work, host-level SSH access has also been available for deployment, diagnostics, logs, source inspection, and controlled repair.

Using SSH to retrieve operational provider data when the MCP path is unavailable would blur the boundary between development access and the governed production interface. It would also weaken the evidence that normal Jason work is passing through identity, authority, capability selection, the Central Orchestrator, provider isolation, and governed result projection.

On 2026-09-21 the Jason MCP connector temporarily returned `UNAVAILABLE` even though the public MCP endpoint was reachable. Host access was used only to diagnose and restart the MCP service. After connector recovery, repeated native MCP status calls succeeded, followed by a governed Datto RMM endpoint read for `AOT-50282` and a governed Autotask ticket read for `T20260921.0017`. Both results returned through Jason MCP with `direct_provider_access=false`.

## Decision

Jason's normal operational data return path is:

`ChatGPT / approved client -> Jason MCP -> Jason identity and authority -> Central Orchestrator -> governed provider connector -> governed result projection -> Jason MCP -> requesting client`

SSH, shell, host filesystem access, container inspection, and direct provider access MUST NOT be used as a fallback mechanism to answer normal operational requests.

SSH and equivalent host-level access are reserved for development and platform operations such as:

- diagnosing Jason itself;
- inspecting deployment/runtime health;
- reviewing logs and source;
- building, testing, deploying, or rolling back Jason components;
- repairing a failed Jason service or transport.

If the MCP operational path is unavailable, the client should report the Jason MCP/platform failure and preserve the requested operational action for retry after the governed path is restored. It should not silently obtain the requested provider data through SSH.

Provider mutations remain governed by the same authority and approval rules regardless of transport health.

## Required behavior

Jason clients and operators MUST:

- prefer the governed MCP capability surface for normal operational reads and actions;
- preserve provider credentials and provider isolation behind Jason;
- return provider-derived operational evidence through the MCP response path;
- treat MCP transport failure as a platform/support condition, not permission to bypass governance;
- use SSH only when the task is explicitly development, deployment, diagnostics, or repair of Jason itself;
- avoid re-dispatching mutations merely because a result/readback transport failed;
- resume idempotent readback through MCP when service is restored.

## Verification

The boundary is considered functioning when:

1. Jason MCP status succeeds from the normal client.
2. Repeated governed calls complete without SSH involvement.
3. At least one Datto RMM operational read returns through MCP.
4. At least one Autotask operational read returns through MCP.
5. Returned MCP status reports `direct_provider_access=false`.
6. Host access is not required to retrieve the operational provider results.

A transport reliability incident may remain open for monitoring even when these boundary checks pass.

## Consequences

### Positive

- preserves one governed operational path;
- keeps development access separate from production operations;
- makes failures visible instead of masking them with an SSH workaround;
- preserves auditability and provider isolation;
- reduces the chance of accidental direct-provider or host-level bypass;
- gives technicians and future agents a simple rule for deciding when SSH is appropriate.

### Costs / constraints

- an MCP outage can temporarily block operational reads even when the provider itself is healthy;
- platform repair may still require host-level access;
- MCP reliability therefore becomes a production dependency and must be monitored accordingly.

## Rejected alternatives

1. **SSH fallback for operational reads** — rejected because it bypasses the normal governed interface and hides transport failures.
2. **Direct provider API fallback** — rejected because provider credentials and execution must remain isolated behind Jason.
3. **Automatic mutation replay after transport failure** — rejected because ambiguous execution state could duplicate provider actions.

## Relationship to existing architecture

This decision extends the same separation-of-responsibilities principle used elsewhere in Jason: interfaces transport requests and results, while Jason identity, authority, policy, orchestration, and provider connectors remain authoritative. Development access is not an operational authority surface.
