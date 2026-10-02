#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_CONTAINER="jason-runtime"
CANDIDATE_IMAGE="${JASON_RUNTIME_CANDIDATE_IMAGE:-}"
PROMOTION_PERMIT="${JASON_PRODUCTION_PROMOTION_PERMIT:-}"
PROMOTION_PLAN_SHA256="${JASON_PRODUCTION_PLAN_SHA256:-}"

PREFLIGHT_ONLY=false
if [ "${1:-}" = "--preflight" ]; then
  PREFLIGHT_ONLY=true
  shift
fi
if [ "$#" -ne 0 ]; then
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=unsupported arguments"
  exit 2
fi

if [ -z "$CANDIDATE_IMAGE" ]; then
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=JASON_RUNTIME_CANDIDATE_IMAGE is required; Production may not build from a checkout"
  exit 42
fi
if ! docker image inspect "$CANDIDATE_IMAGE" >/dev/null 2>&1; then
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=immutable candidate image is not present: $CANDIDATE_IMAGE"
  exit 42
fi

candidate_id="$(docker image inspect "$CANDIDATE_IMAGE" --format '{{.Id}}')"
revision="$(docker image inspect "$CANDIDATE_IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
if [ -z "$revision" ]; then
  revision="$(docker image inspect "$CANDIDATE_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || true)"
fi
case "$candidate_id" in
  sha256:????????????????????????????????????????????????????????????????) ;;
  *) echo "BASELINE_REFRESH=FAIL"; echo "REASON=candidate image ID is not sha256"; exit 42 ;;
esac
case "$revision" in
  ????????????????????????????????????????) ;;
  *) echo "BASELINE_REFRESH=FAIL"; echo "REASON=candidate source revision is not an exact git SHA"; exit 42 ;;
esac

echo "========== JASON PRODUCTION RUNTIME CANDIDATE =========="
echo "SOURCE_REVISION=$revision"
echo "CANDIDATE_IMAGE=$CANDIDATE_IMAGE"
echo "CANDIDATE_IMAGE_ID=$candidate_id"
echo "IMAGE_PROVENANCE=PASS"

if [ "$PREFLIGHT_ONLY" = "true" ]; then
  echo "BASELINE_REFRESH=PREFLIGHT_ONLY"
  exit 0
fi

if [ -z "$PROMOTION_PERMIT" ] || [ -z "$PROMOTION_PLAN_SHA256" ]; then
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=exact-plan Production permit and plan digest are required"
  exit 42
fi

JASON_RUNTIME_PRODUCTION_IMAGE="$CANDIDATE_IMAGE" \
JASON_SOURCE_REVISION_OVERRIDE="$revision" \
JASON_PRODUCTION_PROMOTION_PERMIT="$PROMOTION_PERMIT" \
JASON_PRODUCTION_PLAN_SHA256="$PROMOTION_PLAN_SHA256" \
JASON_PRODUCTION_PROMOTION_OPERATION=deploy \
  bash "$REPO_ROOT/infrastructure/jason-runtime/production-deploy.sh"

python3 "$REPO_ROOT/tools/runtime_cutover_verify.py" \
  --container "$RUNTIME_CONTAINER" \
  --expected-image-id "$candidate_id" \
  --expected-revision "$revision"

running_revision="$(docker inspect "$RUNTIME_CONTAINER" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}')"
running_health="$(docker inspect "$RUNTIME_CONTAINER" --format '{{.State.Health.Status}}')"

echo "RUNNING_IMAGE_MATCH=PASS"
echo "RUNNING_REVISION=$running_revision"
echo "RUNTIME_HEALTH=$running_health"
echo "BASELINE_REFRESH=PASS"
