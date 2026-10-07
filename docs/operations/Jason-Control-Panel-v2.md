# Jason Control Panel v2

## Purpose

`Jason Control Panel — Operations & Configuration` is the unified operator-facing Grafana surface for Jason operations. Grafana is a cockpit and control surface; Jason remains the authority source.

The durable dashboard UID remains `jason-operations-configuration` so existing links and provisioning identity remain stable.

## V2 source contract

The first v2 source slice makes previously placeholder sections authoritative:

- **Scheduled Work** — derived from actual `jason-*.timer` systemd state in both system and user scopes, including activated service, next trigger, last trigger, and last service result.
- **Important System Configuration** — a curated, secret-safe set of operational settings from the live runtime and governed policy files. Each row records its source and required change path.
- **Migration & Upgrade Status** — derived from durable Release Manager records. It shows the release ID, target/source SHA, rollback SHA, actual Release Manager stage, bounded blocker class, production verification proof, rollback verification state, and last durable update time.
- **Navigation** — links into the existing governed Component Control, Playbook Control, Credential Management, Production Health, and Support/TODO surfaces.
- **Dedicated telemetry boundary** — Control Panel metrics are served by `jason-operations-configuration-exporter` on port `9477` and scraped by the `jason-operations-configuration` Prometheus job. They are deliberately not collected inside the latency-sensitive Production Health exporter.

## Migration stages

The dashboard reports actual Release Manager states and does not invent a percentage complete:

`requested -> development -> dev_verified -> release_candidate -> preproduction -> preprod_verified -> production_eligible -> production -> production_verified -> closed`

`blocked`, `failed`, and `rolled_back` remain explicit terminal/intervention states when present.

Failure details are reduced to bounded blocker classes for Prometheus safety, such as `host_reconciliation`, `protected_main`, `documentation_reconciliation`, `preproduction`, `ci_validation`, `provider_canary`, or `other`. Raw error text remains in authoritative Release Manager evidence, not metric labels.

## Configuration safety

The configuration table is intentionally curated. It must not export secrets, arbitrary environment variables, provider credentials, tenant identifiers, or raw provider payloads.

Grafana must never write directly to Autotask, Datto, Microsoft Graph, OpenBao, systemd, Git, or a provider API. Any future configuration edit control must call a narrowly scoped Jason control service that:

1. authenticates and authorizes the operator;
2. validates the exact setting and value;
3. records an audit event;
4. uses the appropriate governed source/runtime change path;
5. preserves protected CI and Release Manager gates;
6. verifies the resulting production state before declaring the change complete.

Existing write-capable surfaces such as Component Control and Credential Management continue to use their dedicated Jason control services.

## Deployment convergence

Host reconciliation installs and verifies the dedicated exporter. Observability reconciliation is conditional: the existing observability release is left untouched for unrelated Jason releases, but changes under `infrastructure/showcase`, the Grafana manifest, or the assurance tooling trigger the normal rollback-protected observability installer. That installer uses the managed engineering Git source with an explicit root-safe Git boundary and must finish with Grafana assurance `PASS`.

## Production hold — 2026-10-07

Owner instruction: build and validate this source change now, but do not merge/promote it to production until the pending root-reconciler sudo bootstrap has been completed and the existing release path is verified healthy.
