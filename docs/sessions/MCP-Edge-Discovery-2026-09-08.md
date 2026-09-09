# MCP Edge Discovery — 2026-09-08

**Classification:** Current discovery evidence  
**Status:** Existing AWS/ZeroTier edge confirmed; relay administration access not yet available from Jason host

## Confirmed current topology

The current Jason host has ZeroTier address `10.87.246.157/24` on network `743993800f93d22f` and can directly reach relay ZeroTier address `10.87.246.16`.

Observed relay connectivity from Jason:

- ICMP: reachable, 0% packet loss during proof;
- TCP 22: reachable;
- TCP 80: reachable;
- TCP 443: reachable;
- TCP 3978: not directly reachable from Jason to the relay, which is consistent with the relay forwarding public ingress toward Jason rather than exposing a listener back toward Jason on that port.

ZeroTier peer observation identifies a direct/known peer path involving public address `18.235.19.103`, matching the documented AWS relay Elastic IP.

Existing durable Teams documentation already identifies:

- AWS relay instance: `i-0b0bb56884acb565c`;
- AWS relay public Elastic IP: `18.235.19.103`;
- relay ZeroTier IP: `10.87.246.16/24`;
- Jason host ZeroTier IP: `10.87.246.157/24`;
- current Teams ingress forwarding through the relay to the Jason host.

## Public edge implementation proof

Fresh HTTP/TLS observation confirms the public relay is running **Caddy**:

- `http://18.235.19.103/` returns `308 Permanent Redirect` with `Server: Caddy`;
- `https://teams-jason.teamaot.com/` returns HTTP/2 through Caddy;
- `https://teams-jason.teamaot.com/api/messages` traverses Caddy and reaches the downstream application path;
- DNS for `teams-jason.teamaot.com` resolves to `18.235.19.103`;
- the relay currently presents a Let's Encrypt certificate for `teams-jason.teamaot.com` valid from 2026-08-10 through 2026-11-08.

This establishes that AOT already operates the principal infrastructure pattern required for a public Jason MCP edge:

```text
public HTTPS / Caddy on AWS relay
        ↓
existing ZeroTier private network
        ↓
current Jason device
```

## Architectural conclusion

Do **not** add a new tunnel provider or additional server before evaluating reuse of the existing AWS relay.

Preferred MCP pilot topology, subject to relay configuration inspection and ChatGPT MCP transport/authentication requirements:

```text
ChatGPT Business
        ↓
new Jason MCP hostname / HTTPS on existing AWS Caddy relay
        ↓
existing ZeroTier network
        ↓
new jason-mcp service on current Jason device
        ↓
Jason governed runtime / Central Orchestrator
```

The Teams hostname/path must remain isolated and unchanged during the MCP pilot. Prefer a separate MCP hostname and distinct upstream port/service rather than modifying the existing Teams route semantics.

## Current blocker

The Jason host does not currently have a usable noninteractive SSH identity for the relay. Attempts using common accounts (`ubuntu`, `ec2-user`, `admin`, `al`) did not authenticate.

The AWS CLI is also not installed on the Jason host, so no AWS control-plane inspection was performed from Jason.

This is an administration-access blocker only. It does not invalidate the technical suitability of the existing relay.

## Next required step

Obtain an authorized administration path to EC2 instance `i-0b0bb56884acb565c` using one of:

1. existing SSH private key and correct instance user;
2. AWS Systems Manager Session Manager if configured;
3. EC2 Instance Connect if configured;
4. AWS console-based authorized access sufficient to inspect Caddy and systemd/service configuration.

Once authorized access exists, inspect only:

- Caddy configuration and service unit;
- current reverse-proxy route for `teams-jason.teamaot.com`;
- ZeroTier interface/state;
- firewall/security group-relevant local listeners;
- available capacity/service-management pattern.

Do not mutate the relay until the current configuration is backed up and the MCP route is designed to coexist independently with Teams.
