# Jason Command Center Showcase

SHOWCASE-001 makes Project Jason visibly observable without changing runtime authority.

## Components

- Grafana provides the human-visible Command Center.
- Prometheus stores showcase and host metrics.
- Node Exporter reports Linux host CPU, memory, filesystem, and related metrics.
- `status_exporter.py` exposes Jason-specific roadmap and component-readiness metrics.
- The machine-readable roadmap is stored in `07-Roadmap/Jason-Roadmap-Status.json`.

## Security boundary

- OpenBao remains on its existing deployment and is not reconfigured by this stack.
- Prometheus is bound to loopback only.
- Grafana is bound to TCP 3000 so the internal administrator can view the dashboard from the LAN.
- Grafana self-registration and analytics reporting are disabled.
- The Grafana administrator password is generated locally into `.env`; it is not committed to Git.
- The status exporter is observational only. It reads roadmap state, Docker container state, and local TCP readiness. It does not execute Jason capabilities or contact external providers.

## Install

From the repository root on the Jason host:

```bash
chmod +x infrastructure/showcase/install_showcase.sh
infrastructure/showcase/install_showcase.sh
```

The script prints the Grafana URL and generated local administrator credential.

## Dashboard

The provisioned `Jason Command Center` dashboard initially shows:

- Jason host availability
- CPU use
- memory use
- root filesystem use
- roadmap completion percentage
- completed milestone count
- roadmap milestone table
- OpenBao health
- OpenClaw gateway health
- local LLM readiness
- Autotask read-capability readiness
- host CPU and memory history

## Local LLM

SHOWCASE-001 intentionally reserves the `Local LLM` dashboard tile but does not install a model runtime. The discovered Jason host has 4 Intel Skylake-era CPU cores, 31 GiB RAM, and no discrete GPU. SHOWCASE-002 should therefore begin with a small quantized CPU model and treat inference as a pilot rather than a high-throughput production workload.
