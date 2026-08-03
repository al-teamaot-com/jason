# ADR-0003: Use Declarative Operation Registries

**Status:** Accepted  
**Decision date:** 2026-08-03

## Context

Provider connectors initially used repeated conditional routing to translate capabilities into provider requests.

## Decision

Use explicit operation registries when multiple operations follow a consistent routing model.

Registries may define:

- method;
- path template;
- path arguments;
- provider parameter mappings;
- optional parameters.

Registries must remain clear and traceable. They must not become hidden metaprogramming systems.

## Consequences

Adding operations usually becomes a data change rather than another conditional branch.

Provider exceptions remain in provider code when they cannot be represented safely or clearly.
