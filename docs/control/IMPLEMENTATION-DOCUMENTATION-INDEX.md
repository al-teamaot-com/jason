# Project Jason Implementation Documentation Index

**Status:** Active documentation control record  
**Owner:** Jason Architecture Authority  
**Purpose:** Make implementation-local documentation discoverable from the `docs/` control plane without copying package-adjacent README files into a second canonical location.

## Why this index exists

Some documentation is most useful beside the code, deployment package, connector, schema, or test harness it explains. J-404 allows that bounded exception because adjacency can reduce implementation mistakes and keep package mechanics synchronized with code.

The exception must not recreate documentation fragmentation.

This index therefore provides one discovery point for implementation-local documentation and states the authority boundary for each category.

## Authority boundary

Implementation-local README files are **supporting implementation documentation**.

They may explain:

- package layout;
- local development and test commands;
- deployment mechanics;
- connector-specific behavior;
- implementation constraints;
- schemas and examples;
- local validation procedures.

They do **not** independently override:

- the Jason Constitution;
- project governance;
- project ADRs;
- canonical J-series architecture;
- governed component/capability specifications;
- identity/authority policy;
- Central Orchestrator authority;
- System Registry operational truth; or
- approved runbooks and security requirements.

If a package README contains a material architecture, authority, security, or operating rule that is not represented by a governed owner under `docs/`, the correct fix is to update the governed owner and link it here. Do not simply promote the README to hidden architecture authority.

## Capability implementation documentation

| Implementation-local record | Supporting purpose | Governed human-facing owner / related records |
|---|---|---|
| `implementation/cap-001/README.md` | CAP-001 reference implementation and developer usage | `docs/components/capabilities/CAP-001-Professional-Ticket-Investigation.md`; `docs/roadmaps/Jason-Capability-Register.md` |
| `implementation/cap-002-observe-backup-config/README.md` | CAP-002 implementation-local guidance | Capability register / applicable capability specification under `docs/components/capabilities/` when promoted |
| `implementation/cap-003/README.md` | CAP-003 implementation-local guidance and validation | Applicable capability and infrastructure records under `docs/components/`; governed roadmap under `docs/roadmaps/` |
| `implementation/cap-007/README.md` | Governed email capability implementation-local guidance | CAP-007 operational and capability records under `docs/components/` and `docs/operations/` |

## Runtime, release, CLI, and convergence documentation

| Implementation-local record | Supporting purpose | Governed human-facing owner / related records |
|---|---|---|
| `implementation/runtime_service/README.md` | Jason runtime-service composition and developer/runtime mechanics | `docs/architecture/`; `docs/components/`; `docs/operations/`; System Registry structured truth for deployed state |
| `implementation/provider_runtime/README.md` | Provider-runtime implementation mechanics | Provider/capability architecture under `docs/engineering/`, `docs/components/`, and relevant operations records |
| `implementation/release/README.md` | Release implementation and validation mechanics | `docs/components/operations/`; `docs/milestones/`; approved release governance |
| `implementation/cli/README.md` | CLI implementation/developer guidance | Governing capability/authority/component documentation for commands exposed by the CLI |
| `implementation/resource_convergence/README.md` | Provider/resource convergence implementation guidance | `docs/engineering/`, canonical models, and infrastructure/component specifications |
| `implementation/client_bootstrap/README.md` | Client bootstrap implementation mechanics | Canonical organizational/client models, identity/authority, and applicable operational runbooks |

## Connector implementation documentation

| Implementation-local record | Supporting purpose | Governed human-facing owner / related records |
|---|---|---|
| `implementation/connectors/datto_rmm/README.md` | Datto RMM connector mechanics | `docs/decisions/ADR-004-Datto-RMM-Managed-Device-Authority.md`; `docs/components/infrastructure/`; provider-neutral connector/JIS guidance under `docs/engineering/` |
| `implementation/connectors/it_glue/README.md` | IT Glue connector mechanics | `docs/components/infrastructure/`; provider-neutral JIS/connector guidance under `docs/engineering/` |
| `implementation/connectors/it_glue_adapter/README.md` | IT Glue adapter implementation details | Canonical provider-neutral contracts and IT Glue infrastructure documentation |
| `implementation/connectors/openclaw/README.md` | OpenClaw connector implementation and transport mechanics | `docs/decisions/ADR-005-OpenClaw-Teams-Transport-Boundary.md`; `docs/decisions/ADR-006-Governed-Conversational-Interface-Routing.md`; `docs/components/infrastructure/INF-014-OpenClaw-Production-Ingress-and-Governance-Gates.md` |
| `implementation/connectors/integration_sdk/README.md` | Integration SDK implementation guidance | JIS engineering architecture under `docs/engineering/jis/` |
| `implementation/connectors/evidence_storage/README.md` | Evidence-storage connector mechanics | `docs/components/infrastructure/INF-013-Artifact-Evidence-Storage-Foundation.md`; evidence/memory architecture |
| `implementation/connectors/microsoft_graph/README.md` | Microsoft Graph connector implementation mechanics | `docs/components/infrastructure/INF-010-Microsoft-Cloud-Platform-Foundation.md`; governed Microsoft operations records |

## Deployment-package documentation

| Implementation-local record | Supporting purpose | Governed human-facing owner / related records |
|---|---|---|
| `infrastructure/jason-runtime/README.md` | Docker/runtime deployment-package mechanics and required deployment inputs | System Registry, `docs/operations/`, runtime/component architecture; never use this README alone to assert current production state |
| `infrastructure/openclaw-jason-bridge/README.md` | OpenClaw Jason bridge deployment/plugin mechanics | ADR-005/ADR-006, INF-014, OpenClaw operational runbooks, System Registry for deployed bridge state |

## How future sessions maintain this index

When a new implementation-local README is introduced or an existing one becomes materially important:

1. confirm adjacency is justified;
2. add the record to this index in the same change;
3. identify its governed human-facing owner or explicitly state that a governing record still needs to be created;
4. ensure the README does not create a competing architecture/governance/current-state source;
5. update or create the governed owner if a durable rule exists only in the README;
6. validate that secret values, client-sensitive evidence, and runtime credentials are not embedded in the README;
7. remove the index entry when the implementation-local record is retired.

## Audit rule

Documentation completeness requires both directions of discoverability:

- a future session beginning in `docs/` can locate material implementation-local guidance through this index; and
- an implementation-local README that depends on important governance or architecture should link or clearly name its governed owner where practical.

The index is not an excuse to keep stale README files. Package-adjacent documentation must evolve with the implementation it describes.

## Current limitations

This index records the implementation/deployment README files identified during the 2026-08-11 documentation consolidation. Future CI should evolve toward automatically inventorying README files outside `docs/` and requiring either an index entry or an explicit non-material exception.
