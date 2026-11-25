# Jason Recovery State Classification

Issue #752 defines the state contract consumed by encrypted recovery export/import.

The machine-readable inventory is config/recovery-state-inventory.v1.json.

The core rule is that recovery classifies state by purpose rather than copying the source machine wholesale.

- Restore durable configuration, policy, authority, audit, workflow, mappings, business state, and required encrypted secret/key material.
- Reconstruct versioned service definitions, networks, images, and caches from released artifacts and configuration.
- Discard ephemeral runtime state.
- Re-enroll machine-bound identities instead of silently transplanting them.

This classification is intentionally path-independent so operator-home paths such as /home/al do not become part of the recovery format.
