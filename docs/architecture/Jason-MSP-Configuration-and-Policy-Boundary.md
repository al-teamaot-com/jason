# Jason MSP Configuration and Policy Boundary

**Status:** Proposed v1.0 deployability contract
**Issue:** #748
**Parent:** #743
**Production impact:** None; design and validation contract only

## Purpose

Jason must exist independently of AOT.

A running instance is defined by:

Jason Release + Deployment Configuration + MSP Configuration + MSP Policy + Secrets + Operational State = Running Jason Instance

Client onboarding is deliberately separate from base installation.

## Configuration taxonomy

### 1. Platform

Immutable released Jason software and generic defaults.

Examples include the Central Orchestrator, governance and approval framework, provider abstraction, audit/evidence framework, deployment/health mechanisms, playbook framework, and generic capability contracts.

Platform code must not require AOT-specific IDs, addresses, queue names, component UIDs, sender domains, provider tenants, or client mappings.

### 2. Deployment configuration

Non-secret facts about one installed Jason instance.

Examples include instance ID, environment, MSP configuration reference, MSP policy reference, state root, secrets-provider profile/reference, timezone, and enabled platform components.

Deployment configuration answers where and as what instance Jason runs, not how AOT chooses to operate.

### 3. MSP configuration

Versioned, validated, non-secret organization-specific integration configuration.

Examples include MSP organization identity, enabled providers, non-secret provider tenant/site IDs, Autotask queue/resource/UDF mappings, Teams target identifiers, communication identities, Datto component/catalog identifiers, provider feature enablement, and capability-bundle selections.

MSP configuration answers what systems and identifiers this MSP uses.

### 4. MSP policy

Versioned operational and governance decisions.

Examples include approval rules, disruption policy, autonomous-safe behavior, ticket admission/ownership rules, client communication rules, escalation policy, human-review policy, evidence requirements, and playbook authority policy.

MSP policy answers what Jason is allowed or expected to do for this MSP.

### 5. Client configuration and mappings

Client-specific provider correlations and durable onboarding facts.

Examples include Autotask company to Datto site mapping, IT Glue organization mapping, DNSFilter organization mapping, client-specific policy exceptions, and device/site associations.

Client data is not required to install Jason. A new instance may start with zero clients and onboard/import them later.

### 6. Secrets

Credentials and cryptographic material such as API credentials, OAuth client secrets, AppRole SecretIDs, signing/private keys, provider tokens, and private certificate material.

Secrets are never embedded in platform source, MSP configuration, MSP policy, client configuration, release artifacts, logs, or approval plans.

Configuration contains only governed secret references or logical names.

### 7. Operational state

Durable runtime state produced or maintained by Jason.

Examples include authority databases, approval/continuation state, audit and orchestration events, playbook run history, provider/client mappings after onboarding, autonomous-work state, resolution memory, procurement state, and model-usage state.

Operational state survives release upgrades and is handled by backup/restore rather than release packaging.

### 8. External prerequisites

Dependencies Jason consumes but does not treat as application state, such as the supported OS, container runtime, DNS/NTP/network, certificate infrastructure, external secret service, and provider APIs.

## Precedence and ownership

The v1.0 precedence model is intentionally narrow:

1. immutable platform defaults;
2. deployment configuration;
3. MSP configuration;
4. MSP policy;
5. durable client configuration/mappings.

Secrets are resolved separately and never participate as ordinary configuration overrides.

Operational state is not configuration and may not silently override configuration or policy authority.

Environment variables and CLI arguments are not general-purpose policy/configuration overlays. They may be used only for a documented allow-list of bootstrap/runtime locators, such as the path to the deployment descriptor or a protected secret-reference file. Every supported environment input must be declared in the configuration contract.

## Revision identity

Every loaded configuration object must have an independently verifiable revision.

For file-backed v1.0 configuration, the canonical revision is the SHA-256 digest of canonical JSON content.

The Deployment Manifest (#750) must report the deployment configuration revision, MSP configuration revision, MSP policy revision, and client-mapping/state identity where applicable.

A configuration change therefore produces a new deployment identity even when application source is unchanged.

## Validation rules

Jason must fail closed before startup/readiness when required schema fields are missing, unsupported schema versions are supplied, unknown configuration keys appear where disallowed, a secret-looking value is supplied where a secret reference is required, Production configuration selects a development-only profile, required configuration/policy cannot be validated, or an MSP/client-specific identifier is required by generic platform code.

## Production rule

Changing Production MSP configuration or MSP policy is a Production change and must participate in the J-CHANGE-003 exact-plan approval boundary even when no application binary/image changes.

## v1.0 migration targets discovered so far

Current runtime examples that must move out of generic platform defaults or operator-home assumptions include AOT Datto component UIDs/names, the AOT default SES sender, Autotask queue/resource/UDF mappings, provider activation profiles, MSP-specific Teams destinations, /home/al KFS secret/install paths, and provider-specific enablement/catalog identifiers.

This contract does not change current Production values. It defines where those values belong in a reproducible deployment.
