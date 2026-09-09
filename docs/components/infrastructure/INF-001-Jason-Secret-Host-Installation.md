# INF-001 Jason Secret Host Installation

## Purpose

This increment installs the canonical `jason-secret` runtime components on the Jason host without creating authentication material, resolving a secret, or authorizing CAP-001 live execution.

## Installed components

The governed command installs and verifies:

- `/opt/jason/lib/jason_secret.py`
- `/usr/local/bin/jason-secret`
- `/etc/jason/secret-mappings.json`

The mapping file contains logical names and provider paths only. It must not contain secret values.

## Non-secret installation mode

The command `tools/deploy_jason_secret_host.py --non-secret-install`:

1. requires root authority;
2. installs the library and launcher;
3. creates the non-production contract mapping when the mapping file is absent;
4. applies canonical permissions;
5. validates installed Python syntax;
6. records artifact paths and SHA-256 hashes;
7. records whether the authentication file exists;
8. records that no OpenBao request or secret resolution occurred.

The authentication file is neither created nor modified by this mode.

## Evidence

Evidence is written outside the repository with mode `0600`. Existing evidence files are never overwritten. The evidence contains no token value or secret value.

## Authorization state

Successful non-secret installation does not make INF-001 deployment-ready. Authentication, OpenBao health, contract resolution, backup/restore verification, ownership, and escalation remain separately governed blockers.

## Required validation

- focused host-installation tests;
- root enforcement test;
- evidence overwrite denial;
- actual installation evidence review;
- checksum and permission verification;
- complete release validation;
- strict documentation build.
