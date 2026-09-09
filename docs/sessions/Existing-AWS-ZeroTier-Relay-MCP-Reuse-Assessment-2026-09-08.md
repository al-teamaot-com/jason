# Existing AWS + ZeroTier Relay MCP Reuse Assessment — 2026-09-08

**Classification:** Architecture/operational assessment  
**Date:** 2026-09-08  
**Status:** Existing relay path confirmed; live relay configuration inspection still required before reuse decision  
**Owner:** Jason Architecture Authority

## Purpose

Determine whether Project Jason already has the external connectivity needed for the new ChatGPT Business + Jason MCP architecture, avoiding a new tunnel service or second Jason server unless the existing path is unsuitable.

## Confirmed existing topology

The active Teams runbook documents an existing public AWS relay and ZeroTier path:

- public DNS: `teams-jason.teamaot.com`;
- public Elastic IP: `18.235.19.103`;
- AWS relay instance: `i-0b0bb56884acb565c`;
- relay ZeroTier IP: `10.87.246.16/24`;
- Jason host ZeroTier IP: `10.87.246.157/24`;
- relay currently forwards the Teams path to the Jason host on TCP `3978`.

The documented current path is:

```text
Microsoft Teams
  -> teams-jason.teamaot.com/api/messages
  -> AWS relay / ZeroTier
  -> Jason host :3978
  -> jason-teams-gateway
  -> Jason Runtime
```

Source: `docs/operations/Runbook-Teams-Integration.md`.

This establishes that Jason already has all of the following in principle:

1. a public AWS edge;
2. a stable public DNS/HTTPS service path;
3. a private ZeroTier network path from that edge to the current Jason device;
4. a production-proven pattern in which the public edge forwards only a bounded service path to a local Jason-owned service.

## Relevance to MCP

ChatGPT requires a remote MCP server endpoint. OpenAI's current guidance says a purely local/private MCP server cannot be connected directly; Secure MCP Tunnel is the recommended path when the MCP server is private/on-prem.

However, Jason's existing AWS relay can potentially satisfy the same reachability requirement without exposing the Jason host directly if the relay can publish a dedicated HTTPS MCP endpoint and proxy it over ZeroTier to a local `jason-mcp` service.

Candidate topology:

```text
ChatGPT Business
    ↓ HTTPS
existing AWS relay / dedicated MCP hostname or path
    ↓ existing ZeroTier private network
current Jason host
    ↓
jason-mcp
    ↓
Jason identity / authority / policy / audit
    ↓
Central Orchestrator
    ↓
governed providers
```

This would preserve the current device as Jason's execution/governance host and avoid introducing another full server or exposing `jason-runtime`/OpenBao directly.

## Reuse decision criteria

The existing relay should be preferred over adding another tunnel product if live inspection proves that it can safely provide:

- HTTPS/TLS for a dedicated MCP endpoint;
- the MCP transport behavior required by current ChatGPT custom apps;
- request/response streaming or connection behavior required by the selected MCP transport;
- forwarding only to a dedicated `jason-mcp` listener on the Jason ZeroTier address;
- no exposure of `jason-runtime:8080`, OpenBao, Docker, or provider APIs;
- request size/timeouts adequate for bounded tool calls;
- identity/authentication pass-through or termination consistent with Jason's identity design;
- independent enable/disable and rollback;
- logging sufficient for edge correlation without storing secrets or unnecessary sensitive payloads;
- coexistence with the existing Teams route without changing its behavior.

## What is not yet confirmed

Repository documentation proves the AWS/ZeroTier path exists, but it does not currently provide enough fresh evidence to assert:

- which reverse proxy/web server is running on the relay;
- its current virtual-host/path configuration;
- current TLS/certificate automation;
- whether the instance remains exactly as documented today;
- whether SSH/SSM/AWS API management access is available from the Jason host/operator context;
- current security-group exposure;
- timeout/buffering settings relevant to MCP;
- whether a new hostname/path can be added without affecting Teams;
- whether current ChatGPT MCP transport requirements are satisfied by the installed edge software/configuration.

Those are operational facts and must be established from fresh observation before mutation.

## Preferred implementation if reuse passes

Do not repurpose the Teams path itself. Add a separate endpoint, for example a dedicated hostname such as `mcp-jason.teamaot.com` or another approved bounded route, while retaining the existing Teams route unchanged.

The relay should terminate public HTTPS and proxy only the MCP endpoint across ZeroTier to a new local Jason MCP service. The MCP service then enters Jason through the governed identity/authority/orchestration boundary.

The relay remains transport only. It must not acquire provider credentials, business authority, provider-selection logic, or direct provider access.

## Fallback order if relay reuse fails

1. OpenAI Secure MCP Tunnel;
2. another governed tunnel such as Cloudflare Tunnel;
3. a separately managed relay only if justified;
4. direct public exposure of the Jason host is not preferred.

## Next evidence step

Collect fresh, non-secret evidence from the current Jason host and, if available, the AWS relay:

- ZeroTier membership/path state;
- route/reachability to `10.87.246.16`;
- current AWS identity/ability to inspect instance `i-0b0bb56884acb565c` without exposing credentials;
- relay service/proxy software and sanitized active configuration;
- current listeners/firewall/security-group state;
- current certificate/hostname layout.

No production change should occur during this inspection.

## Current assessment

**Reuse likelihood: high enough to investigate first.**

A new external tunnel/service should not be introduced until this existing production-proven AWS + ZeroTier edge is shown to be unsuitable for MCP.
