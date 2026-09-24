# DNSFilter / DNS Agent Standing-Safe Production Acceptance — 2026-09-24

## Scope

This record documents production acceptance of the exact read-only Datto RMM component:

- name: `DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026`
- UID: `c3340a58-48d5-457b-bc30-5fd79e5ad8b1`
- corrected script SHA-256: `e499cfbeedc16dc3f2cb2fd4accc40c6e2704f4ac5e77f03b1f8f1065a4ba9ad`

This acceptance does not grant authority to the DNSFilter installer, repair/reinstall, service start/restart, uninstall, DNS/NIC changes, or reboot.

## Live Datto metadata

Authoritative `automation.component.search` returned exactly one matching component with the required live Description:

`Read-only DNSFilter / DNS Agent health collector. Reports installation state, Windows service state, DNSFilter operational logs, Windows event evidence, DNS configuration, and DNSFilter diagnostic lookup results. Performs observation and reporting only.`

The UID remained `c3340a58-48d5-457b-bc30-5fd79e5ad8b1`.

The Description correction removed the earlier keyword false-positive without changing or weakening Jason's global disruptive/destructive classifier.

## Controlled component behavior acceptance

### AOT-50282

- endpoint: `AOT-50282`
- DRMM UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`
- corrected-script acceptance job: `7cdfec79-414e-4425-b499-f13c7dccaa2c`
- result: completed with empty stderr
- classification: clean agent-absent endpoint
- Windows 11 Pro
- .NET Desktop 8 present
- install state absent
- DNS Agent service absent
- Service Manager absent
- normal DNS resolution successful
- DNSFilter TXT diagnostic successful
- no modifying action performed

### AVMAC-1077

- ticket: `T20260924.0021`
- endpoint: `AVMAC-1077`
- DRMM UID: `a95c92ff-5b53-4813-d39a-638d108b48bf`
- corrected-script acceptance job: `985178e1-be58-434d-9b67-6517ec0436bf`
- execution correlation: `corr_mcp_action_2104fafc39b74e54a6a6a118b0747f05`
- Autotask evidence note: `30507964`
- result: completed with empty stderr
- classification: partial/inconsistent DNSFilter installation
- `DNS Agent` present, Stopped, Auto
- `DNS Agent Service Manager` present, Running, Auto
- expected filtering-service executable missing
- Service Manager executable present, version `3.7.11.0`, Authenticode Valid
- normal DNS resolution successful
- DNSFilter TXT verification failed
- 22 relevant Windows events collected
- 30 bounded DNSFilter operational-log findings collected
- diagnostic stopped at diagnosis and did not perform blind reinstall

The AVMAC result proves that partial/corrupt installation evidence must not be collapsed into an "agent missing" classification.

## Durable standing-safe approval

Owner standing-safe approval succeeded after live metadata correction.

- approval mode: `standing_safe`
- approval source: `durable_registry`
- approved by: `person-al`
- approved at: `2026-09-24T12:32:00.007512Z`
- metadata fingerprint: `95500f4e6229ca2b6e21833cc5e041ce284d930d56d9b3f75660a33159fc7549`
- scope: verified managed endpoints
- variables: empty or server-governed only

A subsequent registry readback confirmed the exact UID/name as standing-safe with a metadata fingerprint present.

## No-per-run execution proof

After durable approval, Jason executed the exact component on AOT-50282 without a per-run approval flag.

- job UID: `d951ae82-37e4-406f-bdab-dd192c626d64`
- action correlation: `corr_mcp_action_f91a337e7e5e4cedb3824ed2b52795f2`
- provider attempts: exactly 1
- immediate provider state: accepted / active
- readback verified: true
- terminal state: completed
- terminal read correlation: `corr_mcp_09e87de703ba4825b9f0fa8cb430197e`
- stdout correlation: `corr_mcp_5b18eccd8dc14cb182f2d7870d7679e6`
- stdout was untruncated

The stdout confirmed the same safe absent-agent state and no modifying action.

## Governance conclusions

- `direct_provider_access=false` remained in force.
- Central Orchestrator remained the governed execution path.
- The global disruptive/destructive classifier was not weakened or bypassed.
- The generic PowerShell runner was not promoted.
- `Install DNSFilter AOT Ver 08262024` was not granted standing-safe authority.
- Partial/corrupt installations remain a separate remediation path.
- Service start/restart, repair/reinstall, uninstall, DNS/NIC changes, and reboot remain separately governed.

## Related tracking

- issue #232 — Build standing-safe DNSFilter / DNS Agent diagnostic component
- PR #233 — Add DNSFilter / DNS Agent diagnostic playbook
- PR #233 merged at `d9f105d2272a1a8b6467f65a4226c2fff882ff62`

The diagnostic portion of the DNSFilter playbook is production-ready. The remaining playbook gap is the separately governed installer acceptance/authority decision for genuinely absent agents on eligible endpoints.
