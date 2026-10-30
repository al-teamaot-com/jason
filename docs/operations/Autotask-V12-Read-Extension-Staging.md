# Autotask read expansion — dormant v12 implementation

**Source-only; not activated, not deployed, not a release authorization.**

## Goal
Extend Jason's existing **governed** Autotask read-only query and exact-record
routes to additional *provider-metadata-verified* AOT operational entities.
The API integration must report `canQuery=true` and
`userAccessForQuery=All`. Full API-documentation enumeration and real
record-read proof remain separate from this reviewed source allowlist.

## Source change
Seventeen additional operational entities are listed in
`implementation/connectors/autotask/verified_read_extensions.py`.
They include project phases, task notes and associations, service-call task and
ticket relations, company locations, ticket categories/checklists/secondary
resources/approval associations, and inventory locations/stock details.

The new names are available to the provider GET/query argument compiler
**only** when `JASON_PROVIDER_READ_ACTIVATION_PROFILE` matches the exact
new **v12** value. Existing v10 and v11 profiles retain their previous
selection and permitted query names. The source does not register v12 with
the production activation catalog or Release Manager and does not change
the production activation selection. No provider write operation or
arbitrary provider URL is added. The canonical read adapter continues to
enforce bounded filters, page sizes, exact IDs, and no caller-supplied
provider search JSON.

Autotask's integration user reported `Restricted` rights on two
other reviewed entities and `None` on fifteen (76 metadata-checked
entities total); neither permission class is promoted into this v12
allowlist. Attachments, labor, general resource/HR records and other
sensitive paths remain on their separate authorization controls.

## Release blockers and acceptance
1. Finish already-open v11 native preflight correction and protected
   Production Manager acceptance without changing another active worktree.
2. Confirm true provider record-query availability for each new v12 entity,
   exact-ID and complete cursor pagination, including entity-specific child
   paths. A schema success is **not** a record-read proof.
3. Validate authorized AOT cross-client reads and deny customer-bound
   cross-client disclosure, raw sensitive attachments and secret content.
4. Introduce **separately reviewed** and exact-SHA-bound v12 activation,
   drift monitor identity, rollback to verified v11/v10, and independent
   ticket read canary. No generic activation or source merge constitutes a
   production exception.
5. Observe the Owner's all-promotion freeze until a separate scoped release
   authorization clears it.

The detailed public candidate and live permission evidence is recorded
in `Autotask-Read-Coverage-Matrix-20261027.csv`. None of these changes
can widen existing provider credentials or AOT/customer disclosure authority.
