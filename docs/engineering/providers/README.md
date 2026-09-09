# Project Jason Provider Engineering

**Status:** Supporting implementation-engineering index  
**Owner:** Jason Architecture Authority  
**Higher authority:** Jason Constitution, project ADRs, canonical J-series architecture, JIS engineering guidance, and `docs/engineering/README.md`

## Purpose

This directory contains provider-specific engineering references used to implement and validate integrations beneath Jason's provider-neutral governance model.

Provider documentation describes implementation details and constraints for a particular external platform. It does not make that provider authoritative for Jason as a whole and does not grant execution, identity, secret, or business authority.

## Records

- [Autotask Reference Provider](Autotask-Reference-Provider.md)
- [IT Glue Reference Provider](IT-Glue-Reference-Provider.md)
- [Microsoft Graph Provider](Microsoft-Graph-Provider.md)
- [Microsoft Graph Application Identity](Microsoft-Graph-Application-Identity.md)

## Authority boundary

Provider-specific records remain subordinate to the Constitution, project ADRs, canonical architecture, JIS/provider contracts, identity-first authorization, capability and provider registries, execution policy, Central Orchestrator authority, and System Registry governance.

A provider reference may explain how a platform is integrated; it may not silently redefine Jason's platform model or become the source of truth for current production topology.
