# PMv4 breaker recovery policy custody

The relocated engineering manager runs against a sealed worker source
revision distinct from the verified production last-known-good revision.
The existing native breaker recovery manager must load policy from the
exact production LKG checkout, not that engineering revision. Passing
the worker repository to every stage can leave watchdog-origin breaker
recovery indefinitely waiting for source alignment even after fresh
protected drift observations pass.

Route only the native breaker recovery stage to the established sibling
engineering-source-repo when the pipeline runs against the relocated
engineering-worker-source link. All other stages keep their own source
identity. The native recovery manager's exact LKG and immutable policy
validation, protected root readback, distinct-observation requirement,
cooldown, bounded attempt ledger and independent root transition remain
unchanged. A missing or misaligned policy repository is still a denial;
never use current main as a replacement policy or change repository
HEAD merely to clear a breaker.

This correction is source-only. It neither installs a worker, resets a
breaker, enables an additional service nor changes production controls.
Keep the already reviewed independent-source integration installer and
its exact candidate unchanged. Review and release this small successor
through the existing governed engineering-manager lane only after the
pending predecessor is operationally accepted. No provider or runtime
deployment authority is conveyed.

## Native acceptance of the correction

The successor is restricted to the independently accepted engineering manager
at revision 1c028724328e0a758a59f7a58478e242317b84b1. The existing
signed PipelineSuccessor mechanism, protected CI, release mutex, native
health checks, predecessor receipt and rollback remain mandatory. Only the
pipeline program and its root-owned guard/receipt are changed; the full
closed-loop artifact inventory, including the issue-resolution engine,
remains pinned. Neither runtime nor MCP nor ticket processing is restarted.

The scope binds the established policy repository, exact production LKG
revision and immutable policy SHA-256. Native preflight compares the clean
policy checkout to the root-owned protected release bytes. The same check is
repeated under the existing transaction lock. Two distinct normal scheduled
cycles must record that exact repository for the recovery stage and provide
fresh native closed-breaker evidence for the correct LKG. This demonstrates
the routing correction without deliberately opening the production breaker.
Existing watchdog, quarantine and independent-source acceptance checks remain
required. Any failure uses the existing exact predecessor rollback.
