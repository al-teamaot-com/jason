#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="$REPO_ROOT/infrastructure/jason-runtime/Dockerfile"
RUNTIME_CONTAINER="jason-runtime"
PRODUCTION_IMAGE="jason-runtime:production"
COMPAT_IMAGE="jason-runtime:local"
REVISION_LABEL="org.opencontainers.image.revision"

cd "$REPO_ROOT"

revision="$(git rev-parse HEAD)"
short_revision="$(git rev-parse --short=12 HEAD)"
candidate_image="jason-runtime:candidate-$short_revision"
rollback_alias="jason-runtime:rollback-refresh-$(date -u +%Y%m%dT%H%M%SZ)"

echo "========== JASON PRODUCTION RUNTIME REFRESH =========="
echo "SOURCE_REVISION=$revision"
echo "CANDIDATE_IMAGE=$candidate_image"

old_production_id="$(docker image inspect "$PRODUCTION_IMAGE" --format '{{.Id}}')"
docker tag "$old_production_id" "$rollback_alias"
echo "ROLLBACK_IMAGE=$rollback_alias"

echo "BUILD_BUILDER=default"
docker buildx build   --builder default   --load   --no-cache   --label "$REVISION_LABEL=$revision"   --label "com.teamaot.jason.source_revision=$revision"   --label "com.teamaot.jason.deployment-purpose=production-candidate"   --tag "$candidate_image"   --file "$DOCKERFILE"   "$REPO_ROOT"

candidate_id="$(docker image inspect "$candidate_image" --format '{{.Id}}')"
built_revision="$(docker image inspect "$candidate_image" --format "{{index .Config.Labels \"$REVISION_LABEL\"}}")"
source_revision="$(docker image inspect "$candidate_image" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}')"
test "$built_revision" = "$revision"
test "$source_revision" = "$revision"
echo "IMAGE_PROVENANCE=PASS"

docker run --rm --network none --entrypoint python "$candidate_image" -c   'from orchestrator.service import CentralOrchestrator; from orchestrator.approval_recovery_retry import GovernedApprovalRecoveryRetryExecutor; from jason_runtime.teams_message_send import TeamsMessageSendInvoker; assert hasattr(TeamsMessageSendInvoker,"prepare_execution_plan"); print("ISOLATED_SECURITY_SMOKE=PASS")'

docker tag "$candidate_id" "$PRODUCTION_IMAGE"
docker tag "$candidate_id" "$COMPAT_IMAGE"

restore_aliases() {
  docker tag "$old_production_id" "$PRODUCTION_IMAGE"
  docker tag "$old_production_id" "$COMPAT_IMAGE"
}

if ! JASON_RUNTIME_PRODUCTION_IMAGE="$PRODUCTION_IMAGE"      JASON_SOURCE_REVISION_OVERRIDE="$revision"      bash "$REPO_ROOT/infrastructure/jason-runtime/production-deploy.sh"; then
  restore_aliases
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=production cutover failed; production aliases restored"
  exit 1
fi

running_image_id="$(docker inspect "$RUNTIME_CONTAINER" --format '{{.Image}}')"
running_revision="$(docker inspect "$RUNTIME_CONTAINER" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}')"
running_health="$(docker inspect "$RUNTIME_CONTAINER" --format '{{.State.Health.Status}}')"

if [ "$running_image_id" != "$candidate_id" ]; then
  restore_aliases
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=running image does not match candidate"
  exit 1
fi
if [ "$running_revision" != "$revision" ] || [ "$running_health" != "healthy" ]; then
  restore_aliases
  echo "BASELINE_REFRESH=FAIL"
  echo "REASON=running revision or health verification failed"
  exit 1
fi

echo "RUNNING_IMAGE_MATCH=PASS"
echo "RUNNING_REVISION=$running_revision"
echo "RUNTIME_HEALTH=healthy"
echo "BASELINE_REFRESH=PASS"
