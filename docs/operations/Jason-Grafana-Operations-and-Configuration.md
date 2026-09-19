# Jason Grafana Operations & Configuration

## Section Goal

Give the Owner a concise, secret-safe Grafana view of scheduled Jason work and important production configuration without turning Grafana into a raw configuration dump or a source of execution authority.

## Operator view

Dashboard UID: `jason-operations-configuration`

The page intentionally shows only information likely to matter during normal administration:

- Jason-owned systemd scheduled tasks (`jason-*.timer`), their purpose, enabled/active state, next trigger, previous trigger, and last service result;
- selected governance/deployment settings such as `direct_provider_access`, provider activation profile, Autotask requester mode, Datto execution profile, and expected source revision;
- existing MCP production contract/drift checks;
- existing core production component health.

The dashboard deliberately excludes general Ubuntu housekeeping timers, raw environment-variable dumps, secret values, OpenBao credential material, and low-value implementation settings.

## Authority

Grafana and Prometheus remain observational. A displayed timer, configuration value, or healthy capability grants no provider access, approval, execution authority, or permission to change the system.

## Authoritative sources

Scheduled-task telemetry is derived from the host's current systemd state. Only units matching `jason-*.timer` are included. Calendar timers use their realtime next-trigger value. Monotonic timers are converted to wall-clock time using the host boot uptime.

Curated configuration values are emitted by the existing production-health exporter and use the same secret-safe expected-production contract already used by the Production Health dashboard.

## Verification

Acceptance requires:

1. exporter unit tests pass;
2. production metrics expose all currently installed Jason timers without secret values;
3. Prometheus successfully scrapes the metrics;
4. Grafana provisions `jason-operations-configuration`;
5. the dashboard shows the currently installed Jason timers and curated configuration;
6. existing runtime/MCP/OpenBao workloads are not restarted or changed by deployment.
