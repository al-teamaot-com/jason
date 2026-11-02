# P0: Reuse the authenticated Microsoft/Jason resolver for provider reads

**Source-only. Not deployed. Production freeze ACTIVE.**

## Reproducible wiring defect

The runtime initializes one authenticated
`source_authorization_bindings` resolver for the JKD-001/MS identity
authority path. QuickBooks and other governed invokers already receive
that exact resolver. The Autotask/IT Glue
`build_provider_read_invoker` call *omitted* its existing `bindings`
parameter, forcing the provider read path to construct a **second,
environment-derived, directory-enriched resolver**.

That second resolver can diverge from the authenticated runtime's
identity state, resulting in a service-account fetch being denied by the
requester information-release gate
(`SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED`) even when the upstream
requester has already authenticated and is permitted by JKD-001.

## Minimal correction

Pass `bindings=source_authorization_bindings` to the preexisting
`build_provider_read_invoker` call. The constructor already consumes
this exact instance when supplied. No new credentials, source permissions,
write operations, provider URLs, controller policy, binding schema,
requester-mode changes or customer disclosure authority.

Crucially, this preserves the existing **fail-closed Microsoft Graph
directory enrichment** for user-native provider/IT Glue access. The
alternative of bypassing Graph for all internal Autotask data was
examined and **rejected** because it would alter active-user and
directory-confirmation security semantics without live evidence.

## Validation and release blockers

Regression tests ensure the provider-read builder is invoked with the
same runtime identity resolver and that missing Graph evidence still
fails closed. Other provider/identity/Autotask read tests remain
required.

The historical incident may have involved other session/profile issues;
this concrete wiring defect is not alone proof of the original failure.
No further production release is authorized until protected CI, native
preproduction, signed rollback acceptance and a live authenticated
MCP owner/technician count, all pages, exact read and Projects query
pass under the **new exact SHA**.

This narrow P0 change is coordinated with #2082, which separately
proposes labor/administrator read expansion. That additional functionality
is not necessary to repair the foundational authenticated ticket-read
handoff and is left under its own review/negative permission tests.

## Why the two resolvers were not equivalent

The composition root wraps its durable SQLite binding store in
`AutoEnrollingMicrosoftIdentityBindingStore`, uses it in the bound
Microsoft/Jason runtime identity pipeline, then creates one
`DirectoryEnrichedMicrosoftIdentityBindingResolver(bindings=bindings,
directory=microsoft_directory.directory)`. The old provider read factory
silently rebuilt its own resolver from a **plain**
`SQLiteMicrosoftIdentityBindingStore` and a newly built directory runtime.
Those were not the same authenticated runtime identity path, even when
both referenced the same SQLite file.

Sharing the already-constructed resolver corrects that divergence without
enabling a fallback when directory evidence is unavailable. The
administrator/labor extension in PR #2082 independently proposes the
same constructor injection; it remains a separate, broader permission
change and is intentionally not included in this minimal P0 repair.
