# Read-only client boundary consumers — 2026-11-25

Related: #1117, #2616, #2703.

## Defect and correction

The SharePoint site-control sidecar mounts its authoritative SQLite boundary
database read-only. The existing store constructor nevertheless initializes
and migrates schema and applies chmod. An isolated read-only filesystem
reproduced startup failure with EROFS (errno 30).

The reusable SQLiteClientBoundaryStore now supports an explicit read-only
connection. It requires an existing regular database with the current ordered
schema, uses SQLite mode=ro and query_only, and never initializes, migrates, or
changes file permissions. Existing authority writers retain their default
behavior. The SharePoint sidecar explicitly selects read-only mode; other
runtime callers remain unchanged.

## Verification

* 68 focused boundary, SharePoint runtime, activation, and site-control tests
  passed, including rejection of writes, stale schema, missing files, and
  symlinks; subsequent boundary revocation remains visible.
* The real SharePoint runtime builder successfully opened a synthetic
  validated boundary on an actual read-only single-file systemd bind mount as
  UID/GID 1000 with private networking. A database write was denied.
* The synthetic database bytes and permissions were unchanged. No provider
  requests or production mutations occurred.

## Remaining release gates

This source correction does not authorize installation or site enablement.
The native release mechanism must introduce and verify the shared site-state
volume, read-only credential and boundary projections, and exact rollback
scope. The live authoritative database is presently in DELETE journal mode;
the native launch and recovery path must establish live inode and journal
consistency. Do not substitute an immutable or stale snapshot, mount the
entire authority directory, or permit the sidecar to write authority state.
If WAL, hot-journal recovery, or database replacement prevents safe live
visibility, fail closed until a consistent authorized read-only projection or
governed authority service is available.

Rebuild and verify the site-control image and installation package from the
accepted source. Separately verify the effective client binding, Owner/site
authorization, protected peers, and live access-denial and revocation
behavior before claiming production readiness.
