#!/usr/bin/env bash
set -uo pipefail

# Permission-normalizing wrapper for the rollback-protected production-health
# observability deployment. Some long-lived Jason shells intentionally use
# umask 077, which can cause an isolated Git clone to be unreadable by the
# non-root Prometheus/Grafana container users. This wrapper changes only read
# and directory traverse bits under the showcase source, verifies that Git
# content/mode state remains clean, then invokes the canonical deployment.

REPO_ROOT="${JASON_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
SHOWCASE_DIR="$REPO_ROOT/infrastructure/showcase"
DEPLOY="$SHOWCASE_DIR/deploy_production_health_dashboard.sh"

say() { printf '%s\n' "$*"; }

say "========== NORMALIZE OBSERVABILITY SOURCE ACCESS =========="

if [[ -z "$REPO_ROOT" || ! -d "$SHOWCASE_DIR" || ! -f "$DEPLOY" ]]; then
  say "SOURCE_ACCESS_PRECHECK=FAIL"
  exit 1
fi

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  say "SOURCE_ACCESS_PRECHECK=FAIL_WORKTREE_DIRTY"
  exit 1
fi

# Capital-X adds execute only to directories or files that were already
# executable. This preserves Git's tracked executable-bit contract while
# making source/config trees readable and traversable by monitoring containers.
chmod -R a+rX "$SHOWCASE_DIR" || {
  say "SOURCE_ACCESS_NORMALIZATION=FAIL"
  exit 1
}

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  say "SOURCE_ACCESS_NORMALIZATION=FAIL_GIT_STATE_CHANGED"
  git -C "$REPO_ROOT" status --porcelain
  exit 1
fi

say "SOURCE_ACCESS_NORMALIZATION=PASS"
say "WORKTREE_CLEAN=PASS"
say "SECRET_VALUES_PRINTED=NO"
say

JASON_REPO_ROOT="$REPO_ROOT" bash "$DEPLOY"
exit $?
