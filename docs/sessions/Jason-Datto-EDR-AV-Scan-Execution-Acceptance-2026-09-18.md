# Jason Datto EDR/AV Governed Scan Execution Acceptance — 2026-09-18

## Section Goal

Prove that Jason can start one provider-native Datto AV scan on one exact endpoint through Central Orchestrator, preserve the Project Jason governance boundary, and verify the resulting scan through independent governed status and scan-history reads.

## Scope

Controlled endpoint: `AOT-50282`

- authoritative Datto RMM endpoint UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- authoritative Datto EDR agent ID: `0cf9b495-879b-4b6c-8c60-ac229e01d136`;
- scan type: Quick Scan;
- action capability: `endpoint.security.scan.start`;
- provider-native task name: `Scan - AV Quick`;
- direct provider bypass: prohibited; `direct_provider_access=false` remained authoritative.

No reboot, logoff, service interruption, isolation, quarantine mutation, restore, delete, or other user-disruptive action was part of this acceptance.

## Provider contract

Datto's current EDR client uses the native `POST /api/agents/scan` action. Jason binds that operation to one exact EDR agent and one explicit scan type. The Quick Scan option contract uses AV disk scanning with Quick enabled, Full disabled, forensic scanning disabled, and the provider client compatibility flag `installed=true`.

Jason exposes this only through the provider-neutral governed action `endpoint.security.scan.start`; it is not exposed through the read connector or a generic Datto mutation surface.

## Governance controls proven

The live capability registry reports `endpoint.security.scan.start` as:

- lifecycle: active;
- classification: action;
- risk: medium;
- permission mode: execute;
- approval required: true;
- tenant isolation required: true;
- MCP action enabled: true.

The AOT owner authority grant is exact to `endpoint.security.scan.start`, permission `execute`, with approval required. No broad Datto EDR administer grant was added.

The connector additionally requires:

1. exact endpoint UID;
2. exact EDR agent ID;
3. explicit `quick` or `full`;
4. pre-read confirmation that the agent belongs to the endpoint;
5. Datto AV licensed and enabled;
6. no scan already in progress;
7. Datto's one-scan-per-device-per-hour guard satisfied;
8. one provider mutation attempt only.

## Live acceptance

Before execution, AOT-50282 was online, Datto AV was enabled/connected and engine-ready, no scan was in progress, and the prior Quick Scan was older than one hour.

Jason then issued exactly one governed Quick Scan against the exact endpoint/agent pair through Central Orchestrator. The provider accepted the native scan request.

Independent governed readback proved the new scan:

- `last_av_scan_time`: `2026-09-18T16:25:10.009Z`;
- `last_av_scan_type`: `av-quick-scan`;
- terminal status: `completed`;
- durable scan-history ID: `ba2ad23d-8cb7-4ecf-ac2d-55af309406c3`;
- scan-history type: `Quick scan`;
- scan-history created: `2026-09-18T16:25:14.937Z`.

The provider does not return a durable scan-history ID synchronously from scan start. Jason therefore treats exact endpoint + exact agent + scan type + provider scan timestamp as start evidence and the subsequent governed scan-history record as the durable terminal identity.

## Security-health readback

After completion, governed endpoint-security status still reported:

- endpoint online and active;
- Datto AV enabled and connected;
- AV engine ready;
- no reboot required;
- scan status completed.

A completed scan is not interpreted as a clean security result by itself. Full playbook closure must still combine completed scan evidence with governed post-scan detection/quarantine verification and the originating threat disposition.

## Source and deployment state

The live acceptance scan was initiated on production scan implementation `a7c06f2b45c0d24ca50338312642dc0d68338ef8`. After successful acceptance, the action contract was hardened and production MCP was promoted to `8776ac5dc56c4a22e0f86dceb780f0cff4fd70f9`, adding the explicit `datto_edr.execution` logical secret alias and matching Datto's client payload with `installed=true`. All relevant CI workflows passed before the hardened promotion. A second live scan was not issued immediately because the provider's one-hour scan guard must be respected.

## Acceptance disposition

**SUPPORT-CAP-013: RESOLVED.**

**Governed provider-native Datto AV scan start: ACCEPTED.**

Quick and Full scan initiation are now available through the same bounded governed capability. Quick Scan is proven live; Full Scan uses the mutually exclusive provider option in the same tested action contract but was not separately launched during this acceptance.

The overall Datto EDR/AV threat-response playbook remains `pilot` and `enabled=false` pending the complete remediation/scan/post-scan-verification/recurrence acceptance path.
