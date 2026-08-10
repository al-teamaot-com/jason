# Jason Grafana Deployment Baseline

This directory provides a local, version-controlled Grafana deployment baseline for Jason's operational console.

It is a bootstrap artifact, not production approval.

## Purpose

The deployment mounts the Jason dashboard provisioning and dashboard JSON from `implementation/management_console/grafana/` into Grafana read-only. Grafana persists only its own runtime database and local state in the `grafana-data` Docker volume.

Grafana remains a presentation layer. It is not trusted to authorize Jason operations and it must not receive provider credentials or raw secret values.

## Prerequisites

- Docker with Compose support.
- The external Docker network `jason-core` already exists.
- A local `.env` created from `.env.example`.

## Start

From this directory:

```bash
cp .env.example .env
# Replace GRAFANA_ADMIN_PASSWORD before continuing.
docker compose up -d
```

The baseline binds Grafana to loopback only on port 3000 by default. Remote exposure, reverse proxying, TLS, SSO, and production identity integration require separate governed deployment work.

## Version policy

The baseline is pinned to Grafana `13.1.1` rather than `latest` so deployment changes are deliberate and reviewable. The Technology Steward process should review Grafana releases, security fixes, API/plugin changes, and retirement opportunities before changing the pinned version.

## Security defaults

The bootstrap configuration:

- requires an explicit administrator password;
- disables anonymous access;
- disables user self-registration;
- disables Gravatar;
- disables Grafana usage reporting and automatic update checks;
- mounts Jason dashboard/provisioning source read-only;
- binds the web port to `127.0.0.1`;
- applies `no-new-privileges` to the container.

These settings reduce accidental exposure but do not constitute a complete production hardening profile.

## Production prerequisites

Before this console is exposed beyond localhost, separately design and approve:

1. TLS and reverse-proxy topology.
2. TeamAOT identity/SSO integration and MFA expectations.
3. Grafana role mapping and least-privilege administration.
4. Jason principal propagation for Management API requests.
5. Server-side authenticated access to Jason data sources.
6. Backup and recovery of Grafana state where required.
7. Log retention and audit ownership.
8. Patch/update ownership and Technology Steward review cadence.
9. Network isolation and firewall rules.
10. Removal or disablement of bootstrap administrator access when an approved identity path exists.

Grafana RBAC remains additive. Jason independently authorizes every governed action using Jason identity, organization, policy, approval, and capability controls.

## Current data state

The provisioned dashboard is presently a read-only shell. It documents the planned Management API sources but does not yet contain live Jason queries. The next implementation slice is to expose and connect the first safe read-only endpoints:

- `/system/health`
- `/capabilities`
- `/providers`
- `/audit/events`

No state-changing capability should be wired into Grafana during this bootstrap phase.
