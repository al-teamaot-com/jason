# Jason Short-Term Priorities

**Status:** Accepted near-term roadmap direction  
**Date:** 2026-09-13

## Immediate sequence

1. Complete governed write/update capability for **Autotask**, **Datto RMM (DRMM)**, and **IT Glue**.
2. Immediately after those write capabilities are proven safe, implement **Continuous Documentation Assurance** as a short-term priority.
3. Use that documentation foundation to support broader operational autonomy, proactive technical management, and management-by-exception.

## Continuous Documentation Assurance

Jason should be responsible for proactively driving AOT and client documentation toward a known complete, current, and verified state.

Jason should not wait for a technician or owner to point out a missing item. It should compare expected documentation against available evidence and detect gaps, stale records, conflicts, and unverified information on its own.

The core workflow is:

**Detect gap → create work → pursue → validate → document → verify → close → monitor freshness**

### Example: missing DNS / domain registrar credentials

If Jason determines that a client has a registered domain but AOT does not have the required registrar/DNS credentials or authoritative access information documented, Jason should:

1. confirm that the documentation requirement is genuinely missing and not merely stored elsewhere;
2. search authorized authoritative sources before asking a human for information;
3. if the gap cannot be resolved from existing evidence, create an Autotask documentation-gap ticket identifying what is missing, why it matters, the affected client/domain, and what constitutes completion;
4. route or assign the request to the appropriate technician/client contact according to policy;
5. monitor the ticket and relevant authorized communications for a response;
6. follow up and escalate according to normal AOT workflow if the request is ignored or incomplete;
7. validate the information received before treating the gap as resolved;
8. update the correct IT Glue object/credential location using governed write capability;
9. never place secret material in Autotask ticket notes or other inappropriate systems of record;
10. update the Autotask ticket with a safe completion note and reference rather than the secret itself;
11. verify that the IT Glue documentation now exists in the expected state;
12. close the documentation-gap ticket only after verification;
13. retain provenance and a future freshness/reverification expectation where appropriate.

## General documentation behavior

Jason should apply the same closed-loop pattern to other required documentation, including items such as ISP credentials and circuit information, firewall access, domain and DNS ownership, Microsoft tenant relationships, backup/recovery information, LOB applications and vendors, escalation contacts, software licensing, warranties, network diagrams, recovery procedures, and other managed-client operational knowledge.

Jason should classify documentation state at minimum as:

- **Missing** — required information does not exist in the expected system of record.
- **Stale** — information exists but is older than the accepted verification interval or conflicts with newer evidence.
- **Conflicting** — authoritative sources disagree.
- **Unverified** — information exists but its provenance or accuracy is not sufficient.
- **Verified** — required information exists and is supported by current authoritative evidence.

## Definition of done

For operational work that creates or changes durable knowledge, documentation is part of completion:

**Resolve → Verify → Document → Verify documentation → Close**

Jason should not consider a documentation-gap workflow complete merely because a ticket was created or because someone supplied information. Completion requires the appropriate system of record to be updated and verified.

## Governance boundary

Jason may automatically fill documentation gaps only when the fact is supported by authoritative evidence and the applicable write authority permits the change.

Jason must not invent missing facts, silently infer credentials, expose secrets in ticket notes, or cross client/tenant boundaries. Unknowns should remain explicit until verified.
