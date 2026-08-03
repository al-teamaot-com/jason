# JIS Provider Specification Template

Use this template when creating or materially revising a Jason Integration SDK provider.

## 1. Provider Identity

**Provider name:**  
**External platform:**  
**Provider owner:**  
**Technology Steward:**  
**Environment:**  
**Status:** Proposed / Foundation / Production Validated / Active / Retired

## 2. Purpose

Describe the business requirement and the outcomes this provider enables.

## 3. Scope

### Included

- 

### Excluded

- 

## 4. Official Platform References

List the authoritative vendor documentation used to implement and validate the provider.

## 5. Authentication

Document:

- provider authentication method;
- least-privilege provider identity;
- read identity;
- write identity, when applicable;
- token or credential lifetime;
- rotation process;
- regional or tenant endpoint behavior.

## 6. Logical Secrets

**Logical read secret:**  
**Logical write secret:**  
**OpenBao path:**  
**Approved fields:**  
**Bootstrap identity path:**  

Do not include credential values.

## 7. Supported Capabilities

List each registered Jason capability and its purpose.

| Capability | Mode | Risk | Description |
|---|---|---|---|
|  |  |  |  |

## 8. Operation Registry

Document the registry location and the operation-definition fields used by the provider.

## 9. Generic Entity Gateway

**Supported:** Yes / No / Partial

### Approved entities

| Jason entity name | Provider resource | Get | Query | Notes |
|---|---|---|---|---|
|  |  |  |  |  |

Explain why excluded resources are not approved.

## 10. Provider-Specific Behavior

Document behavior that must remain inside the provider, such as:

- endpoint discovery;
- authentication exchange;
- JSON conventions;
- field translation;
- pagination;
- rate limits;
- webhook behavior;
- provider-specific errors.

## 11. Read and Mutation Boundaries

Describe:

- read-only operations;
- proposed mutations;
- approval requirements;
- business-reason requirements;
- idempotency;
- verification;
- rollback or compensating actions.

## 12. Audit Requirements

Document required audit events and prohibited audit content.

## 13. Testing

List:

- focused provider tests;
- shared JIS tests;
- negative authorization tests;
- secret-safety tests;
- malformed argument tests;
- mutation tests, when applicable.

## 14. Production Validation

Record:

- validation date;
- validator;
- environment;
- operations tested;
- expected permissions;
- result;
- known restrictions.

Do not record secrets, tokens, private keys, or sensitive client data.

## 15. Known Limitations

- 

## 16. Operational Procedures

Reference:

- provisioning;
- credential rotation;
- failure handling;
- health checks;
- incident response;
- provider retirement.

## 17. Technology Steward Review

**Review interval:**  
**Vendor-change sources:**  
**Retirement criteria for custom code:**  

## 18. Completion Checklist

Reference `JIS-Provider-Completion-Checklist.md`.
