# Jason Command Center Showcase

SHOWCASE-001 makes Project Jason visibly observable without changing runtime authority. The Command Center now also reflects the later local-LLM and Autotask business-context milestones built on top of the original showcase.

## Components

- Grafana provides the human-visible Command Center.
- Prometheus stores showcase and host metrics.
- Node Exporter reports Linux host CPU, memory, filesystem, and related metrics.
- `status_exporter.py` exposes Jason-specific roadmap and component-readiness metrics.
- The machine-readable roadmap is stored in `07-Roadmap/Jason-Roadmap-Status.json`.
- Ollama provides the loopback-only local model runtime used by governed local-AI capabilities.

## Security boundary

- OpenBao remains on its existing deployment and is not reconfigured by this stack.
- Prometheus is bound to loopback only.
- Grafana is bound to TCP 3000 so the internal administrator can view the dashboard from the LAN.
- Grafana self-registration and analytics reporting are disabled.
- The Grafana administrator password is generated locally into `.env`; it is not committed to Git.
- Ollama is bound to loopback only.
- The status exporter is observational only. It reads roadmap state, Docker container state, local TCP readiness, and local model readiness. It does not execute Jason capabilities or contact external providers.
- Dashboard status never grants capability authority. Execution remains subject to normal Jason governance, orchestration, policy, and audit boundaries.

## Install

From the repository root on the Jason host:

```bash
chmod +x infrastructure/showcase/install_showcase.sh
infrastructure/showcase/install_showcase.sh
```

The script prints the Grafana URL and generated local administrator credential.

## Dashboard

The provisioned `Jason Command Center` dashboard shows:

- Jason host availability;
- CPU use;
- memory use;
- root filesystem use;
- roadmap completion percentage;
- completed milestone count;
- roadmap milestone table;
- OpenBao health;
- OpenClaw Gateway health;
- local LLM readiness;
- canonical Autotask read-capability readiness;
- CAP-003 Autotask Business Context milestone state; and
- host CPU and memory history.

The roadmap table is sourced from the machine-readable roadmap, so CAP-002 remains visibly identified as a transitional proof while CAP-003 convergence is still in progress.

## Local LLM

SHOWCASE-002 deployed CPU-only Ollama with `qwen3:1.7b` on the Jason host. The host has 4 Intel Skylake-era CPU cores, 31 GiB RAM, and no discrete GPU, so local inference remains a governed pilot rather than a high-throughput production service.

The local runtime has been validated for structured JSON responses and is used by CAP-003 through a loopback-only endpoint. CAP-003 projects only bounded business-relevant Autotask fields into the model context rather than sending entire raw provider objects.

## CAP-003 visible milestone

CAP-003 Autotask Business Context completed its first governed live validation on 2026-08-07.

The validated path was:

`operator request -> Central Orchestrator -> canonical Autotask reads -> bounded business context -> local Qwen model -> briefing/evidence -> durable orchestration completion`

The validation resolved Autotask company ID `208`, read contacts, configurations, tickets, contracts, and projects through observe-only capabilities, generated a local business briefing, wrote protected evidence outside the repository, and made no provider-side change.

CAP-003 remains `in_progress` until ticket-analysis parity is proven and the transitional CAP-002 implementation can be retired without leaving duplicate capabilities.
