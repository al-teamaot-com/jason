# Triage Intelligence Engine

The Triage Intelligence Engine helps Jason decide whether a reported symptom is an actual fault, expected platform behavior, a known vendor issue, a local environmental change, or a previously solved AOT pattern before recommending remediation.

## Core question

> Should we be trying to fix this, or is the reported behavior explained by a known change, policy, rollout, incident, or prior resolution?

## Processing flow

```text
Ticket
  -> symptom normalization
  -> product and environment identification
  -> platform intelligence lookup
  -> known-issue lookup
  -> historical AOT ticket lookup
  -> recent-change correlation
  -> environment evidence lookup
  -> risk review
  -> ranked findings
  -> recommendation
```

## Design principles

- Recommendation-first and read-only during the initial pilot.
- Deterministic policy and evidence rules remain authoritative.
- AI may normalize language, compare evidence, and explain findings, but may not invent sources or bypass policy.
- Every finding must identify its evidence source, freshness, confidence, and scope.
- Vendor changes, internal history, and device evidence must remain distinguishable.
- A match to expected behavior does not automatically close a ticket.
- Cross-client data must be aggregated or explicitly authorized.
- Agents never call data providers directly; the orchestrator invokes registered providers.

## Intelligence domains

- Platform intelligence: releases, feature changes, removals, deprecations, rollout rings, known issues, and mitigations.
- Historical intelligence: prior AOT tickets, resolutions, technician notes, and recurrence patterns.
- Environment intelligence: installed updates, application versions, policies, device health, licensing, and configuration.
- Change intelligence: recent deployments, patches, policy changes, configuration drift, and service incidents.
- Knowledge intelligence: official vendor documentation and approved internal standards.
- Risk intelligence: security, compliance, operational impact, and business urgency.

## Initial capabilities

- `triage.ticket.assess`
- `triage.symptoms.normalize`
- `triage.expected_behavior.detect`
- `triage.known_issue.match`
- `triage.history.match`
- `triage.change.correlate`
- `triage.recommendation.build`

## Outcomes

- `expected_behavior`
- `known_vendor_issue`
- `known_internal_pattern`
- `environment_change`
- `probable_fault`
- `security_or_compliance_risk`
- `insufficient_evidence`

## Initial pilot

The first pilot should use Autotask ticket text plus read-only device, patch, policy, and vendor-intelligence evidence. Results should appear as a technician-facing report and should not alter tickets or devices automatically.
