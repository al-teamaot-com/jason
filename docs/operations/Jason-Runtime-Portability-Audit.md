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

## Runtime Compose extraction progress

The generic runtime Compose no longer embeds AOT-specific deployment defaults.

The portability migration:
- removes the default AOT Datto component list and scalar component identity;
- preserves fail-closed Datto behavior by defaulting server-configured component scope to empty while allowing separately governed durable approvals;
- renames the procurement web-read profile to the provider-neutral procurement-web-v1 identifier;
- requires the SES default sender to be supplied explicitly by deployment/MSP configuration;
- removes the AOT sender default from runtime composition;
- moves the KFS history password host mount default to the canonical Jason runtime-secrets tree.

After this extraction, infrastructure/jason-runtime/compose.yaml has zero portability-audit blockers.

The remaining portability findings are operator-home dependencies in legacy/service assets and are handled separately.

## Zero-blocker service/path milestone

The declared deployable runtime and service assets now pass the portability audit with zero blockers and zero warnings.

The service-path migration removes the original operator account and workstation-home assumptions from the audited deployment surface:

- engineering source checkout defaults to /var/lib/jason/source;
- engineering worktrees default to /var/lib/jason/worktrees;
- service-home state defaults to /var/lib/jason/service-home;
- GitHub CLI/runtime credential state lives under /var/lib/jason/runtime-secrets;
- KFS service/runtime/evidence/secrets use /opt/jason and /var/lib/jason paths;
- CCC uses the jason service account and canonical evidence/recovery paths;
- documentation and repair workers use configured repository identity rather than assuming the AOT GitHub repository;
- production-host reconciliation uses the configured Jason service account rather than user al.

This is a source/candidate portability result. It does not change any currently installed Production unit or running process.

## MCP deployment identity portability

The generic MCP server no longer embeds AOT-specific Entra or host defaults.

MCP deployment identity is now loaded through a dependency-free configuration contract:

- Entra tenant ID is explicit;
- Entra client ID is explicit;
- auto-enroll domains default to empty;
- resource URL defaults only to loopback;
- OAuth issuer defaults from the configured resource URL;
- allowed Host values derive from the configured resource URL unless explicitly supplied;
- allowed Origin values remain explicit/generic and may be overridden by deployment configuration.

The MCP server entrypoint fails closed when required tenant/client deployment identity is missing.

The portability audit now scans the generic MCP server for AOT domain, tenant-ID, and client-ID literals so these assumptions cannot silently return.
