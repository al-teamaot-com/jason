# INF-001 Jason Secret Host Deployment

## Status

Foundation implementation. Host installation remains a separate governed action.

## Purpose

This increment deploys the canonical `jason-secret` wrapper to the Jason host without exposing authentication material or enabling CAP-001 live execution prematurely.

## Canonical paths

| Item | Path |
|---|---|
| Wrapper library | `/opt/jason/lib/jason_secret.py` |
| Command launcher | `/usr/local/bin/jason-secret` |
| Logical mapping file | `/etc/jason/secret-mappings.json` |
| OpenBao authentication file | `/etc/jason/openbao.token` |

The authentication file path is documented; its contents must never be committed, logged, copied into evidence, or printed.

## Deployment command

`tools/deploy_jason_secret_host.py` performs the governed installation and emits non-secret evidence containing only paths, hashes, and health status.

The command:

- requires root for host changes;
- rejects authentication files readable by group or world;
- installs the wrapper and launcher with executable permissions;
- creates a logical-name mapping file only when one does not already exist;
- validates wrapper health without resolving or printing a secret;
- refuses to overwrite an existing evidence file.

## Initial mapping boundary

The foundation may create only the non-production logical reference `jason.contract-test`. Production Autotask mappings must be introduced in a later governed increment after authentication and contract testing are proven.

## Readiness boundary

Successful installation does not by itself authorize CAP-001 live reads. The deployment record must remain blocked until all required authentication, mapping, contract-test, backup, restore, ownership, and escalation facts are verified.
