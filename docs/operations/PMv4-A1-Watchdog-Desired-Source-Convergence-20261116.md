# PMv4 A1 — reconcile protected Git watchdog source with already-installed root policy

**November 16, 2026: SOURCE-ONLY reconciliation. No new root policy,
Owner approval, release activation, drift-watchdog disable, or production
service change is authorized or performed by this Git integration.**

The Owner already approved and completed a separate exact one-container
root policy admission `pmv4-a1-exact-one-container-root-watchdog-admission-v1`.
That exact root transaction committed the optional
`jason-pmv4-shadow-gateway` name under
`allowed_running_containers` on the active root-protected overlay,
while preserving `required_containers` and all other fields.
The signed root postflight verified target SHA256
`9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804`,
with original root bytes archived for rollback. The installed root overlay
may contain unrelated historical authorized entries absent from this Git
source; no wholesale replacement of that overlay is permitted.

The protected Git `main` source SHA
`33044085e1df5ad430ec7f29492801ac7219d4a8`
still omitted the optional shadow name. This small PR adds **only**
that exact name to `allowed_running_containers` to align the source
declaration with previously signed live intent. It does **not** make
the shadow required, and does not grant any other container permission.
Four source tests compare exact JSON to this immutable main baseline,
verify optional absence and presence, and ensure that an unrelated
container still causes drift. GitHub's existing protected required checks
remain mandatory.

Integration coordination: #2500 #2391

#2500 contains the historical
source and exact Owner root admission tooling used to apply the existing
policy but is behind protected main and should not be merged wholesale;
this PR carries only its exact one-container source delta. #2391 touches
`allowed_system_units`, not the container allowlist, and must be
reconciled independently if it proceeds. Neither grants authority to
deploy A1 or retire PMv3.

J-CHANGE-001 requires A1 production candidates to be pinned to the
**new exact merged main SHA**. The previous unapproved source packet
at `33044085...` remains immutable historical evidence; it cannot be
silently relabeled or given a fresh approval after this source merge.
Recreate the offline OCI image label and immutable A1 v2 candidate packet
from the final merged source, rerun required CI, preflight and native
rollback acceptance. The failed original A1 approval
`owner-mcp-319c697027a146beac98818e5305a971`
remains consumed/rollback-only and is never reused.
