# Jason Runtime Portability Audit

Issue #748 requires Jason platform/runtime material to be separable from AOT and operator-host configuration.

The runtime portability audit is a non-production gate over declared deployable runtime assets.

It currently blocks on:
- operator-home paths;
- AOT email-domain defaults;
- AOT component labels;
- AOT-specific runtime/profile identifiers.

The audit reports only the matched fragment, rule, file, and line number. It does not echo complete runtime configuration lines.

A candidate release is not considered clean-deployable while blocker findings remain. The correct remediation is to move the value into validated MSP/deployment configuration or remove the host-specific dependency, not to add an allow-bypass environment flag.
