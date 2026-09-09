# Jason Integration SDK Engineering Guide

**Status:** Supporting implementation-engineering index  
**Owner:** Jason Architecture Authority  
**Higher authority:** Jason Constitution, project ADRs, canonical J-series architecture, and `docs/engineering/README.md`

## Purpose

This directory contains detailed Jason Integration SDK (JIS) engineering guidance for building provider integrations beneath Jason's governed platform architecture.

JIS is an implementation-engineering layer. It does not create independent authority to select providers, access secrets, bypass identity or policy gates, or execute outside the Central Orchestrator.

## Records

- [Provider Development Guide](JIS-Provider-Development-Guide.md) — primary engineering guide for provider development.
- [Provider Template](JIS-Provider-Template.md) — bounded template for new provider work.
- [Provider Completion Checklist](JIS-Provider-Completion-Checklist.md) — completion evidence and readiness checks.
- [Milestone Closeout Policy](JIS-Milestone-Closeout-Policy.md) — closeout expectations for JIS milestones.
- [Microsoft Graph Technician Onboarding](Microsoft-Graph-Technician-Onboarding.md) — provider-specific technician onboarding guidance.

## Authority boundary

Use the records in this directory to implement governed integrations. When a JIS record conflicts with the Constitution, a project-level ADR, canonical J-series architecture, identity/authority controls, the Capability Registry, the Execution Provider Registry, the Central Orchestrator, or System Registry governance, the higher-authority record governs and the engineering documentation must be reconciled.
