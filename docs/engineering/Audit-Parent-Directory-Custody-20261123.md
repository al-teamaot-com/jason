# Audit installer parent-directory custody correction

Status: source engineering; no production ownership or archive changes.

The live privileged preflight rejected `/var/lib/jason` because it applied the Root installation-parent contract to the existing service-account data directory. Live metadata is UID/GID 1000:1000, mode 0750. Changing that shared data directory to satisfy an incorrect Root assumption risks unrelated Jason workflows.

The installer now checks `/var/lib` as the Root-controlled parent for new privileged state, alongside the original Root-owned code, policy and service parents. It separately checks `/var/lib/jason` with its exact existing service-account UID/GID and mode. The existing native directory guard is unchanged. Neither check changes ownership or permissions; group/other write, symlink, wrong UID, wrong GID and incorrect data-directory mode still deny admission before any data or Owner action.

Regression coverage invokes the actual preflight parent phase with the native guard. The isolated native Root fixture also creates the real Root/service-account directory topology and exercises positive admission plus negative custody cases without Host mounts or production paths. The prior fixture covered installation composition, but not the parent admission phase; this coverage gap is now closed.

Previously completed integrity proof remains usable within its native validity period. This correction does not require another full-database scan, change the production freeze, issue Owner authority, or perform archive adoption. Exact protected-Main CI, privileged preflight, independent Owner authentication, rollback and end-to-end archive acceptance still apply.
