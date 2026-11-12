# J-Assist isolated pilot — reuse existing Jason and AWS relay

**State:** Source-only preparation. **NOT deployed, NOT authorized to activate**, and not a functional screenshot receiver yet. This package deliberately serves HTTP 503 for any J-Assist intake/readiness request.

## Reuse decision

Use the **current Jason Linux host** for one separate, non-root J-Assist container and the **existing AWS HTTPS relay + ZeroTier private path** for an optional, path-limited connection to that container. Preserve the existing `mcp-jason.teamaot.com` hostname and TLS identity. Do **not** create another EC2 host, ECS cluster, load balancer, VPC, NAT gateway, DNS record, ACM certificate, ECR repository or IAM role. Do not reuse Connectly's application credentials or service: its `connectly-dev` ECS cluster is a separate product, currently without running tasks, and an ECS image store / persistent evidence layer would introduce additional services and resources.

Verified read-only inventory on 2026-11-12:

| Existing asset | Observed |
| --- | --- |
| Jason host | Linux x86-64, 4 logical CPUs, 31 GiB memory (about 26 GiB available), about 41 GiB free disk |
| AWS account / region | `887670144825` / `us-east-1` |
| Existing relay EC2 | `i-0b0bb56884acb565c`, `Jason-Teams-Relay`, t3.micro, running |
| Relay EIP and DNS | `18.235.19.103`, `mcp-jason.teamaot.com` |
| Existing DNS hosted zone | `teamaot.com` / `Z02444982FY651WQ3RXFU` |
| Existing relay inbound SG | 80/443; **no new public application port** |
| Existing private relay network | ZeroTier; Jason `10.87.246.157` reached `10.87.246.16` by read-only route/ping on Nov 12; verify relay identity and config before any route change |
| Existing AWS ECS | `connectly-dev` Fargate service desired 0, unrelated; **not used** |
| New AWS resource count | **0** |
| AWS mutations performed | **0** |

## Exact new local footprint (not yet created)

| Category | Requirement |
| --- | --- |
| Container | `jassist-pilot`, separate Docker network `jassist-isolated`; **not attached** to existing runtime, MCP, OpenClaw or Teams Docker networks |
| CPU / RAM | 0.50 CPU max / 768 MiB RAM max (pilot with external, approved content reviewer; re-evaluate if scanning locally) |
| Processes | 64 PID limit; 1 ASGI worker |
| Ephemeral workspace | 64 MiB `/tmp` tmpfs, `noexec,nosuid,nodev` |
| Persistent evidence plan | 1,024 MiB allocated/quotad encrypted host filesystem, *future*: `/var/lib/jason/pilots/jassist`; separate session and image SQLite files under private 0700 directory / 0600 files; **not mounted in disabled build** |
| Evidence boundary | Maximum 1 MiB JPEG, up to 256 live receipts, AES-256-GCM, two separately governed 32-byte keys, 120-second image expiry, purge every 60 seconds, replay nonce window 300 seconds |
| Privileges | UID:GID 10001:10001, read-only container root, all Linux capabilities dropped, no-new-privileges, **no Docker socket, no provider vault, no prod state bind mounts** |
| Network while disabled | Host loopback `127.0.0.1:3981` only; private Docker bridge with `internal:true`, therefore no external provider egress |
| Network when separately approved | Proposed exact Caddy `/v1/jassist/*` path forwarding through existing ZeroTier to `10.87.246.157:3981`; host firewall permits **only** verified AWS relay peer `10.87.246.16`; no direct Internet access to port 3981 |
| Existing browser | Current J-Assist 0.2.2 pinned to `https://mcp-jason.teamaot.com`, no new Chrome hostname |
| Logs | Auth result, receipt ID, policy revision, timing and digest only; no bearer, screenshot bytes, session secret or full request body |

The 1 GiB evidence *quota* is a requirement for the later activated service; the source-only disabled Compose configuration contains no persistent database mount and **does not itself configure a disk quota**. Do not claim a quota, at-rest disk encryption, purge service or DLP is operational until those are installed and independently tested.

## Separate, governed activation gates (all still required)

1. Independently inspect and back up the **current** AWS relay Caddy configuration. Reverify the ZeroTier IPs, trusted TLS chain, existing MCP/Teams/other HTTPS routes, host firewall and exact path ordering. The `caddy-route.PROPOSED.caddy` fragment is review material, **not** an approved or installed Caddy configuration.
2. Preserve existing production service routing. Add an isolated pilot path only under a separately authorized, exact-reviewed relay change; the Owner **did not authorize any production changes** in the screenshot-pilot instruction. No production service restart/reload or host firewall change without exact permission.
3. Use existing AOT Entra identity: tenant `f7054323-d52b-4863-8c2f-1898f0b6077c`, group `AOT-Jason-JAssist-Users` / `5273dd8a-1456-4985-b0a3-c00061267e26`, signed delegated `JAssist.Send` scope, individual technician mapping and server-side live user-enabled + group check. For a server-owned Microsoft Graph app, verify existing admin-consented **User.Read.All** and **GroupMember.Read.All** as needed for the current `GET /users/{id}` plus `POST /users/{id}/checkMemberGroups` strategy; do not silently grant them.
4. Reuse the governed Jason **read-only Datto capability**, including native numeric ID → UUID pairing from **PR #2456** and the exact pinned AOT site/device state. No direct Datto API key or browser-asserted permissions in the pilot container.
5. Bind existing governed secret source to exactly two independent AES-256-GCM keys; no plaintext key environment variables or image/keys in Docker build layers. Bind an approved content-review/DLP implementation with a strict, independently tested rejection policy; no pass-through reviewer.
6. Provide an explicit, reviewed **allowlisted outbound path** to Microsoft Graph/Entra JWKS and existing governed device-read authority. The default `internal:true` network cannot contact any provider and must not be bypassed merely to make a green readiness response.
7. Wire the existing `JAssistRuntimeDependencies` and `JAssistASGIGateway` to a reviewed pilot ASGI entrypoint with independent exact-action release approval. The current `disabled_app.py` is *intentionally inactive*. Do not repoint live production MCP tools or ticket-processing containers.
8. Independently verify signed-in AOT technician, reviewer readiness, scoped CORS, TLS, SHA-256 receipt, same-technician MCP image read, revocation, expiry, purge, replay and rollback using the approved **non-sensitive AOT device**. No screenshot upload is permitted before these checks pass.

### Source-only validation

The files `Dockerfile`, `requirements.pilot.txt`, `compose.pilot.yaml`, `disabled_app.py` and `resource-plan.yaml` describe a reproducible **inert** service. No command in this package mutates AWS; it intentionally includes no deploy, apply, start, restart or release script. Test with `python -m unittest discover -s infrastructure/jassist-pilot/tests -p 'test_*.py'`.

**Do not use the draft route, run the container or load real secrets solely because these source tests pass.** No existing AWS services, permissions or production Jason services have been changed.

## Activation and rollback transaction (NOT authorized now)

A future separately approved exact-release transaction must first read and
cryptographically retain the live Caddy config, existing production health,
MCP OAuth/Teams route evidence, current host firewall state, image digest,
policy, and currently protected rollback SHA. Stage the new **isolated**
container with dedicated quota, encrypted sessions/images, keys, approved
content review and live provider proofs; verify via loopback with non-sensitive
test data and revoke/replay tests. Only then authorize an exact bounded
`/v1/jassist/*` Caddy route and relay-only ZeroTier firewall rule. Do not
reload Caddy or restart production containers until separately approved.
If the acceptance check fails, remove **only** the pilot route and container,
restore the backed-up exact Caddy configuration and firewall delta, and verify
unchanged MCP/Teams/Autotask ticket processing. This is a plan, not an
executed rollback. Existing SSM agent is **online** on the relay, but
whether the operator has approved SSM session rights to edit Caddy remains
unverified; the currently used `jason-readonly` profile is read-only.
