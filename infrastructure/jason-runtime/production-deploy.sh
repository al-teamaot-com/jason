#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_RUNTIME_PRODUCTION_IMAGE:-jason-runtime:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"
PROMOTION_PERMIT="${JASON_PRODUCTION_PROMOTION_PERMIT:-}"
PROMOTION_PLAN_SHA256="${JASON_PRODUCTION_PLAN_SHA256:-}"
PROMOTION_OPERATION="${JASON_PRODUCTION_PROMOTION_OPERATION:-deploy}"

if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
fi

PREFLIGHT=false
for arg in "$@"; do
  if [ "$arg" = "--preflight" ]; then
    PREFLIGHT=true
  fi
done

PROMOTION_ARGS=()
if [ "$PREFLIGHT" != "true" ]; then
  if [ -z "$PROMOTION_PERMIT" ] || [ -z "$PROMOTION_PLAN_SHA256" ]; then
    echo "PRODUCTION_PROMOTION_GATE=FAIL missing exact-plan permit or plan digest" >&2
    exit 42
  fi
  PROMOTION_ARGS=(
    --production-permit "$PROMOTION_PERMIT"
    --promotion-plan-sha256 "$PROMOTION_PLAN_SHA256"
    --promotion-component "jason-runtime"
    --promotion-operation "$PROMOTION_OPERATION"
  )
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK="jason-runtime-rollback-$STAMP"

python3 "$REPO_ROOT/tools/deploy_live_container.py" \
  --live jason-runtime \
  --image "$IMAGE" \
  --rollback "$ROLLBACK" \
  --source-revision "$REVISION" \
  --harden \
  --promote-image-tag jason-runtime:production \
  --promote-image-tag jason-runtime:local \
  --rollback-image-tag jason-runtime:rollback-current \
  --health-url http://127.0.0.1:8080/healthz \
  "${PROMOTION_ARGS[@]}" \
  "$@"
