# ADR-0004: Use Governed Generic Entity Gateways

**Status:** Accepted  
**Decision date:** 2026-08-03

## Context

Many provider APIs expose consistent operations across multiple entity or resource types. Implementing separate connector code for every entity would create unnecessary duplication.

## Decision

Use generic entity gateways where the provider API supports a consistent model.

Generic gateways must use explicit approved entity mappings or equivalent governed discovery.

User input must never provide unrestricted access to arbitrary provider paths.

Provider-specific capabilities remain appropriate when operations require specialized endpoints, validation, or result handling.

## Consequences

Approved entities can be added with limited connector changes.

The approved entity catalog becomes a security boundary and requires review.
