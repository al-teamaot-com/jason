# ADR-0001: Establish the Jason Integration SDK

**Status:** Accepted  
**Decision date:** 2026-08-03

## Context

Project Jason integrates multiple external platforms. Independent implementation paths would duplicate authentication, secret handling, auditing, transport, testing, and governance logic.

## Decision

Establish the Jason Integration SDK (JIS) as the standard governed integration framework for external platforms.

All interfaces use JIS rather than communicating directly with providers.

JIS contains shared integration infrastructure while provider-specific behavior remains within provider packages.

## Consequences

### Positive

- consistent governance;
- reusable infrastructure;
- fewer direct integrations;
- simpler provider development;
- shared tests and operational patterns.

### Negative

- shared JIS changes require careful compatibility review;
- providers with unusual APIs may need documented exceptions.

## Governing principle

Generalize infrastructure. Specialize capabilities.
