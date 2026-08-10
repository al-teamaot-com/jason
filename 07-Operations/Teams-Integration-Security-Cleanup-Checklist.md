# Teams Integration Security Cleanup Checklist

This checklist captures hardening work that should follow the successful 2026-08-10 proof-of-concept.

## Immediate

- [ ] Replace mode `0644` on `jason-approval-bot-combined.pem` with least-privilege ownership/group and mode `0640` or tighter.
- [ ] Confirm only the OpenClaw runtime identity and authorized administrators can read the private key.
- [ ] Delete `/tmp/jason_graph_token` after testing.
- [ ] Ensure future Graph tokens are memory-only or short-lived protected runtime artifacts.
- [ ] Run `openclaw secrets audit --check`.
- [ ] Run `openclaw security audit --deep`.

## OpenClaw governance

- [ ] Configure `commands.ownerAllowFrom` for the designated command owner.
- [ ] Set `plugins.allow` explicitly after confirming plugin IDs for `codex` and `msteams`.
- [ ] Migrate `gateway.auth.token` and other plaintext secret-bearing fields to SecretRefs/OpenBao-backed references.
- [ ] Record OpenClaw Teams provider and configuration version in the capability registry.

## Microsoft Graph / Entra

- [ ] Record business justification for `TeamsAppInstallation.ReadWriteForUser.All`.
- [ ] Set a Technology Steward review interval for the broader permission.
- [ ] Define retirement criteria: remove broader permission if `TeamsAppInstallation.ReadWriteSelfForUser.All` becomes sufficient in the tenant.
- [ ] Keep app-catalog publication permissions separate from Jason runtime permissions.
- [ ] Define certificate rotation procedure and expiry monitoring.

## AWS relay

- [ ] Document why ports 80 and 443 are internet-accessible.
- [ ] Confirm port 80 is retained only if needed for certificate/bootstrap behavior; remove if no longer necessary.
- [ ] Enable/verify CloudWatch or equivalent monitoring for relay health and Caddy failures.
- [ ] Confirm SSM remains the administrative access path and no unnecessary SSH ingress exists.
- [ ] Review Elastic IP allocation and lifecycle ownership.

## ZeroTier

- [ ] Confirm only required Jason and relay members are authorized on the network.
- [ ] Document ZeroTier membership approval/revocation process.
- [ ] Add monitoring for relay-to-Jason connectivity.

## Audit/evidence

- [ ] Record Graph request IDs/correlation IDs for install operations.
- [ ] Record Teams message IDs and conversation references by secure reference.
- [ ] Add capability version, workflow ID, target identity, and policy decision to every proactive message audit event.
- [ ] Do not store message content in evidence unless required by business/compliance policy; prefer content hashes/references where appropriate.
