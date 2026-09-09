# INF-013 — Artifact and Evidence Storage Foundation

## Purpose

INF-013 defines the provider-neutral boundary for storing and referencing large artifacts and governed evidence in Project Jason.

Jason agents must not copy large artifacts or evidence payloads between agents. Artifacts are stored centrally through an orchestrator-approved storage capability and passed by immutable reference.

## Core contract

Every admitted artifact records:

- organization/client scope;
- artifact kind and media type;
- sensitivity classification;
- source capability and operation;
- correlation identifier;
- immutable artifact identifier;
- SHA-256 content digest and byte size;
- storage provider and opaque storage locator;
- creation timestamp.

The reference does not contain the artifact payload.

## Governance rules

1. The active organization context must exactly match the artifact organization.
2. Empty artifacts are denied.
3. Source capability, operation, correlation ID, storage provider, and storage locator are mandatory.
4. Storage locators are references, not authority. A caller still requires permission to retrieve the artifact.
5. Artifact relationships do not grant execution authority.
6. Physical storage and retrieval occur only through Central Orchestrator-approved capabilities.
7. Agents may return structured artifact references; they may not communicate artifact bytes directly to other agents.
8. Sensitivity classification must be preserved across storage, retrieval, export, retention, and deletion workflows.

## Initial artifact kinds

- evidence;
- report;
- export;
- attachment;
- transcript;
- snapshot.

## Initial sensitivity classes

- internal;
- client confidential;
- security sensitive;
- regulated.

## Provider strategy

This contract deliberately does not select a single storage product. Local evidence storage, SharePoint/OneDrive, object storage, or another approved provider can implement the physical storage capability without changing the canonical reference model.

This follows Jason's integrate-before-innovate rule: use an existing platform when it satisfies the requirement rather than building a bespoke blob store.

## Relationship to other foundations

- INF-011 resource gateway may return artifact references for exports and attachments.
- INF-012 relationship evidence may reference supporting artifacts.
- Microsoft, Autotask, Datto RMM, IT Glue, and security-platform capabilities may emit evidence through this boundary.
- Approval workflows may attach decision evidence by reference.
- Audit events should record artifact IDs and digests rather than protected payloads.

## Safety boundary

The foundation performs no physical storage, retrieval, deletion, provider request, or cross-tenant access. It creates a governed reference only after admission checks pass.

## Validation

Before merge:

1. run `implementation/connectors/tests/test_artifact_evidence.py`;
2. run the complete connector suite;
3. run Kernel and release validation;
4. run strict documentation validation;
5. verify no artifact payload or credential is committed to the repository.

## Next binding

After validation, select and bind the first physical evidence store through the capability registry. The binding must preserve organization isolation, sensitivity metadata, immutable digest verification, retention policy, and retrieval authorization.
