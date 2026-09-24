#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_RUNTIME_PRODUCTION_IMAGE:-jason-runtime:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"

if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK="jason-runtime-rollback-$STAMP"

exec python3 "$REPO_ROOT/tools/deploy_live_container.py"   --live jason-runtime   --image "$IMAGE"   --rollback "$ROLLBACK"   --source-revision "$REVISION"   --harden \
  --promote-image-tag jason-runtime:production \
  --promote-image-tag jason-runtime:local \
  --rollback-image-tag jason-runtime:rollback-current \
  --health-url http://127.0.0.1:8080/healthz   "$@"
