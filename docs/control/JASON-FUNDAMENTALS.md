# Project Jason — Fundamentals Baseline

**Status:** Active continuity index  
**Owner:** Jason Architecture Authority  
**Authority:** This document is a discovery and reconstruction index only. It does not supersede the Constitution, approved governance, canonical architecture, standards, ADRs, System Registry, code, schemas, tests, or observed evidence.  
**Purpose:** Prevent future human or AI sessions from rediscovering Jason's basic operating model before useful work can continue.

## Mandatory startup rule

Before proposing architecture, creating a provider/connector, capability/resource, agent, gate, ingress/interface, authority component, secret integration, internal service, or changing an existing Jason boundary, read this baseline and the linked authoritative records.

Do not reconstruct Jason's fundamentals from chat history, memory, code archaeology, or whichever implementation happens to be easiest to find.

If this baseline conflicts with a higher-authority source, the higher-authority source wins and this baseline must be corrected in the same workstream.

## Fundamentals that must not be rediscovered

| Fundamental | Durable rule | Authoritative starting source |
|---|---|---|
| Mission | Jason exists to help TeamAOT deliver better, more consistent, scalable service to clients; security/compliance are capabilities, not Jason's whole identity. | `docs/foundation/` and the Jason Canon/Constitutional records |
| Governance | Human/organizational authority remains explicit. Technical access does not create business authority. | `docs/foundation/J-002-Constitution.md`, `docs/governance/` |
| Orchestration | The Central Orchestrator is the sole coordination/execution authority. Agents, connectors, and providers do not coordinate around it. | `docs/architecture/J-100-Reference-Architecture.md`, `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` |
| Agent boundaries | Agents never invoke or communicate with other agents directly. They return structured results or request named capabilities through the orchestrator. | Constitution/governance plus canonical architecture |
| Capability/resource model | Jason prefers reusable, discoverable capabilities/resources over bespoke workflow scripts. Capability/provider resolution is governed rather than hard-coded into conversational behavior. | `docs/architecture/J-101-Capability-Registry.md`, `docs/engineering/capabilities/Capability-Registry.md` |
| Provider/connector model | External-system access lives behind governed provider/connector boundaries and follows JIS. Interfaces and agents must not bypass JIS/provider governance. | `docs/engineering/jis/JIS-Provider-Development-Guide.md` |
| Identity and authority | Identity is established before authority; permissions are capability/scope specific; missing authority fails closed. | `docs/components/kernel/JKD-001-Identity-and-Authority-Service.md` and related JKD-001 records |
| Policy/gates | Consequential actions pass through the applicable governance/policy/approval gates. Gates do not become hidden workflow logic inside connectors or agents. | `docs/architecture/J-102-Governed-Approval-Architecture.md`, `docs/components/kernel/JKD-004-Execution-Policy-Engine.md` |
| Evidence | Evidence comes before assertion. Provenance, correlation, sanitization, and durable proof are part of the platform contract. | `docs/components/kernel/JKD-002-Evidence-and-Memory-Service.md` plus capability/runbook records |
| Secrets | Secret values are never stored in documentation, System Registry records, prompts, handoffs, or ordinary audit evidence. Use governed credential references and the secrets broker. | `docs/components/kernel/JKD-003-Secrets-Broker.md`, `docs/operations/Provider-Secret-Provisioning.md` |
| Operational topology | Jason must be able to describe and verify its current operational topology. Current production state comes from System Registry structured truth plus observed verification, not narrative memory. | `docs/architecture/J-103-System-Registry.md`, `implementation/kernel/system_registry/` |
| Documentation | Durable project knowledge belongs in the governed documentation control plane; one material fact has one authoritative owner. | `docs/standards/J-404-Documentation-Governance-and-Continuity.md`, `docs/control/HOW-TO-DOCUMENT-JASON.md` |
| Platform integrity | No component may bypass approved orchestration, authority, policy, provider, secret, client-isolation, audit, or operational-registration boundaries merely because a direct technical path exists. | `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` |
| Integrate before innovate | Prefer existing platform capabilities and reusable Jason capabilities before creating custom code or tightly coupled workflows. Custom code requires justification and retirement criteria. | Constitution/architecture/standards and relevant ADRs |

## Mandatory workstream startup sequence

For any material Jason workstream:

1. Read `docs/control/JASON-FUNDAMENTALS.md`.
2. Read `docs/control/CURRENT.md` for the current resume point.
3. Read `docs/control/EXTENSION-CONSTRUCTION-MAP.md` if the work creates or changes an extensible Jason component.
4. Locate the authoritative records through `docs/control/DOCUMENTATION-REGISTER.md`.
5. Read the governing architecture, standard, ADR, component contract, and existing construction guide for the component class.
6. Inspect an existing analogous implementation and its deterministic tests only after the governing rules are known.
7. Inspect current Git and System Registry/host evidence before asserting current production state.

The purpose of the existing implementation inspection is to reuse a known pattern, not to reverse-engineer the platform's fundamentals.

## No-rediscovery rule

If a workstream discovers that a fundamental implementation pattern is necessary but is not documented well enough to reproduce safely, treat that as a documentation defect.

Do not repeatedly solve the same design question from first principles.

Before completing the workstream:

- update the appropriate construction guidance;
- update `docs/control/EXTENSION-CONSTRUCTION-MAP.md`;
- update the governing architecture/standard if the durable rule changed;
- add or update conformance tests where the rule is mechanically enforceable; and
- update `docs/control/CURRENT.md` when the safe resume point changes.

## Reconstruction test

A future competent human or AI session, with only the repository and no conversation history, must be able to answer before making a material change:

- what component class is being changed;
- what authority governs it;
- what it may and may not call directly;
- how identity, authority, policy, approvals, evidence, secrets, and audit apply;
- where it is registered;
- how it is tested and verified;
- how production state is observed;
- how it is disabled, rolled back, deprecated, or retired; and
- which existing implementation should be used as the closest governed example.

If those answers require reconstructing fundamentals from code archaeology or prior chats, Jason's continuity documentation is incomplete.
