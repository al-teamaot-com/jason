#!/usr/bin/env bash

# Refresh the local Jason runtime image from the current repository revision without
# using the custom jason-builder BuildKit instance, then recreate the proven
# non-dynamic Teams baseline through jason-ops.sh.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="$REPO_ROOT/infrastructure/jason-runtime/Dockerfile"
IMAGE="jason-runtime:local"
REVISION_LABEL="org.opencontainers.image.revision"

cd "$REPO_ROOT" || return 1 2>/dev/null || exit 1

revision="$(git rev-parse HEAD 2>/dev/null)"
if [ -z "$revision" ]; then
    echo "BASELINE_REFRESH=FAIL"
    echo "REASON=unable to resolve repository revision"
    return 1 2>/dev/null || exit 1
fi

echo "========== JASON BASELINE IMAGE REFRESH =========="
echo "SOURCE_REVISION=$revision"

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    old_image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null)"
    if [ -n "$old_image_id" ]; then
        rollback_tag="jason-runtime:rollback-refresh-$(date +%Y%m%d-%H%M%S)"
        docker image tag "$old_image_id" "$rollback_tag"
        echo "ROLLBACK_IMAGE=$rollback_tag"
    fi
fi

# The host's custom buildx builder previously failed deterministically while
# exporting/importing this image. Use Docker's default buildx builder explicitly so
# a source refresh does not reuse that failing deployment path.
echo "BUILD_BUILDER=default"
if ! docker buildx build \
    --builder default \
    --load \
    --label "$REVISION_LABEL=$revision" \
    --tag "$IMAGE" \
    --file "$DOCKERFILE" \
    "$REPO_ROOT"; then
    echo "BASELINE_REFRESH=FAIL"
    echo "REASON=default-builder image refresh failed"
    return 1 2>/dev/null || exit 1
fi

built_revision="$(docker image inspect --format "{{index .Config.Labels \"$REVISION_LABEL\"}}" "$IMAGE" 2>/dev/null)"
if [ "$built_revision" != "$revision" ]; then
    echo "BASELINE_REFRESH=FAIL"
    echo "REASON=image provenance does not match repository revision"
    echo "IMAGE_REVISION=${built_revision:-missing}"
    return 1 2>/dev/null || exit 1
fi

echo "IMAGE_PROVENANCE=PASS"
echo "IMAGE_REVISION=$built_revision"

if ! bash "$REPO_ROOT/infrastructure/jason-runtime/jason-ops.sh" baseline-deploy; then
    echo "BASELINE_REFRESH=FAIL"
    echo "REASON=baseline recreation failed after image refresh"
    return 1 2>/dev/null || exit 1
fi

echo "BASELINE_REFRESH=PASS"
