# Teams Integration Security Cleanup Checklist

**Status:** Active hardening backlog  
**Updated:** 2026-08-15  
**Current inbound architecture:** Direct Jason Teams Gateway under ADR-009  
**Current proof:** `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

This checklist tracks security/hardening work after the successful Microsoft Teams foundations and the 2026-08-15 direct-ingress production cutover. Items here are hardening tasks unless explicitly identified as a production blocker.

## Direct Teams gateway

- [x] Establish a dedicated non-intelligent Teams ingress service outside the OpenClaw model/agent loop.
  - Container: `jason-teams-gateway`.
  - Host port ownership proven: `3978 -> 3979`.
  - OpenClaw remained healthy on `18789-18790`.
- [x] Append a dedicated Microsoft application credential for the direct gateway without reading, replacing, or deleting the existing OpenClaw credential.
- [x] Store the dedicated migration credential without printing the value.
  - Current host path: `/opt/jason/services/jason-teams-gateway/msteams.env`.
  - Protection at creation: mode `0600`.
- [x] Register the gateway, credential reference, deployment topology, and proof in the System Registry/lifecycle record.
- [x] Preserve a production rollback path before transferring host port 3978.
- [x] Prove a live Datto-backed Teams request through the direct gateway with no corresponding OpenClaw model dispatch.
- [ ] Migrate the direct gateway credential from the host environment file into Jason's governed secret-delivery architecture or certificate/federated authentication.
- [ ] Define and test rotation/revocation for the dedicated gateway credential before its first scheduled rotation.
- [ ] Revoke retired/obsolete Teams application credentials after migration/rollback requirements no longer depend on them.
- [ ] Add credential expiry/rotation monitoring without exposing secret values.
- [ ] Periodically confirm host port 3978 remains exclusively owned by `jason-teams-gateway`.

## OpenClaw Teams boundary

- [x] Remove OpenClaw from externally reachable ordinary inbound Teams ingress by releasing host port 3978.
- [ ] Review whether OpenClaw's internal `msteams` provider/listener can be disabled for inbound use without breaking approved outbound/proactive messaging.
- [ ] If outbound/proactive Teams is moved away from OpenClaw, disable/remove the dormant `msteams` provider and update ADR-005/ADR-007/System Registry in the same governed workstream.
- [ ] Configure `commands.ownerAllowFrom` for the designated OpenClaw command owner where still applicable.
- [ ] Set `plugins.allow` explicitly after confirming required trusted plugin IDs.
- [ ] Migrate `gateway.auth.token` and other plaintext secret-bearing OpenClaw fields to SecretRefs/OpenBao-backed references.
- [ ] Run `openclaw secrets audit --check` after the next OpenClaw security-maintenance window.
- [ ] Run `openclaw security audit --deep` after the next OpenClaw security-maintenance window.

## Historical OpenClaw certificate hardening

- [x] Replace mode `0644` on `jason-approval-bot-combined.pem` with least-privilege ownership/group and mode `0640` or tighter.
  - Completed 2026-08-10.
  - Host path: `/opt/jason/bootstrap/secrets/microsoft-teams/jason-approval-bot-combined.pem`.
  - Final host mode: `0640` (`-rw-r-----`).
  - File owner: `root`.
  - Group is numeric GID `1000`; the host displays this as `al`, while the OpenClaw container maps GID `1000` to group `node`.
- [x] Confirm only the OpenClaw runtime group and authorized administrators can read the combined private-key PEM.
  - OpenClaw runtime identity verified as `uid=1000(node) gid=1000(node) groups=1000(node)`.
  - Container read test returned `[PASS] OpenClaw can read combined PEM`.
  - Outbound Teams regression test after hardening returned `deliveryStatus: sent`.
- [ ] Re-evaluate whether the combined OpenClaw certificate/private-key file is still required after inbound cutover and future outbound/proactive transport decisions.

## Microsoft Graph / Entra

- [ ] Confirm `/tmp/jason_graph_token` from the original proof no longer exists; remove it if still present.
- [ ] Ensure future Graph tokens are memory-only or short-lived protected runtime artifacts.
- [ ] Record/retain business justification for `TeamsAppInstallation.ReadWriteForUser.All` while proactive user installation still depends on it.
- [ ] Set a Technology Steward review interval for the broader installation permission.
- [ ] Retirement criterion: remove broader permission if `TeamsAppInstallation.ReadWriteSelfForUser.All` becomes sufficient or if proactive bootstrap moves to another governed transport.
- [ ] Keep app-catalog publication permissions separate from Jason runtime permissions.
- [ ] Keep direct-gateway authentication permission scope separate from Graph proactive-install permission scope.
- [ ] Maintain certificate/client-credential rotation procedures and expiry monitoring.

## AWS relay

- [ ] Document why ports 80 and 443 are internet-accessible.
- [ ] Confirm port 80 is retained only if needed for certificate/bootstrap behavior; remove if no longer necessary.
- [ ] Enable/verify CloudWatch or equivalent monitoring for relay health and Caddy failures.
- [ ] Confirm SSM remains the administrative access path and no unnecessary SSH ingress exists.
- [ ] Review Elastic IP allocation and lifecycle ownership.
- [ ] Monitor relay-to-Jason `3978` reachability without sending unauthenticated production messages.

## ZeroTier

- [ ] Confirm only required Jason and relay members are authorized on the network.
- [ ] Document ZeroTier membership approval/revocation process.
- [ ] Add monitoring for relay-to-Jason connectivity.
- [ ] Confirm the relay reaches the direct gateway owner rather than an accidental OpenClaw 3978 publication after service/Compose changes.

## Audit / evidence

- [x] Preserve direct-gateway production proof without storing Microsoft client-secret values.
- [x] Preserve System Registry lifecycle events for the direct gateway credential reference, gateway component, and updated deployment topology.
- [ ] Record Graph request IDs/correlation IDs for future proactive install operations.
- [ ] Record Teams message IDs and conversation references by secure reference when required for troubleshooting/evidence; avoid unnecessary duplication in narrative documentation.
- [ ] Add capability version, workflow ID, target identity, and policy decision to every proactive message audit event.
- [ ] Do not store message content in evidence unless required by business/compliance policy; prefer content hashes/references where appropriate.
- [ ] Add a periodic topology verification proving the direct gateway owns host 3978, OpenClaw does not publish 3978, and Jason Runtime remains healthy.

## Completion boundary

The direct inbound routing work is already operational and production-proven. This checklist is complete only when remaining secret-delivery, permission-review, OpenClaw residual-listener, relay/network monitoring, and periodic topology-verification items have been governed and evidenced.
