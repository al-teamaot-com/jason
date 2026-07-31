# J-403 — Canonical Sources and Generated Artifacts

**Version:** 0.1  
**Status:** Approved engineering standard  
**Owner:** Jason Architecture Authority

## Purpose

This standard defines the boundary between authoritative source material and derived outputs created for publishing, indexing, deployment, reporting, or other consumption.

## 1. Canonical authority

Every governed record, configuration, specification, policy, decision, or knowledge artifact shall have one authoritative canonical source.

Generated or published representations shall not become authoritative merely because they are easier to access or consume.

## 2. Generated artifacts

Generated artifacts are derived representations of canonical sources.

Examples include:

- documentation websites;
- temporary documentation trees;
- reports;
- diagrams;
- indexes;
- API documentation;
- search indexes;
- AI ingestion packages;
- exports to external knowledge systems;
- packaged deployment artifacts.

Generated artifacts must never be edited manually.

## 3. Deterministic generation

A build process shall produce equivalent outputs when given equivalent canonical inputs and build configuration.

Generation logic shall be:

- versioned;
- reviewable;
- understandable;
- testable;
- reversible;
- capable of failing clearly when required inputs are missing.

## 4. Disposable outputs

Generated outputs must be safe to delete and regenerate.

Their loss must not destroy authoritative knowledge, policy, evidence, or configuration.

## 5. Source control

Canonical sources shall be committed to source control unless prohibited by security, privacy, licensing, or operational constraints.

Generated artifacts shall not be committed by default.

Any exception requires explicit justification, ownership, review criteria, and retirement criteria.

## 6. Traceability

Where practical, generated outputs should be traceable to:

- source files;
- source revision;
- generator version;
- build configuration;
- generation time;
- correlation or build identifier.

Traceability metadata must not contain secret values.

## 7. Consumer independence

Publishing, indexing, search, AI ingestion, website generation, external documentation systems, and similar consumers are replaceable implementations.

No consumer may redefine Jason's canonical knowledge model or become the authoritative source.

Consumers must adapt to Jason's canonical sources.

## 8. Generated workspace

The repository-local `.build/` directory is the standard workspace for disposable generated artifacts unless a specific tool requires another approved location.

The `site/` directory is reserved for generated static-site output.

Both directories shall be excluded from source control.

## 9. Security

Build processes must not copy secrets, credentials, runtime databases, audit logs, backup snapshots, private keys, tokens, or other prohibited data into generated outputs.

Generated-output pipelines must fail closed when source classification or authorization is indeterminate.

## 10. Governing rule

Canonical knowledge is authored and governed.

Generated artifacts are derived and disposable.

Consumers never become sources of authority.
