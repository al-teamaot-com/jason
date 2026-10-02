#!/bin/sh
set -eu

: "${JASON_KFS_RUNTIME_IMAGE:?JASON_KFS_RUNTIME_IMAGE must identify an immutable Jason runtime image}"

exec /usr/bin/docker run --rm --user 0:0 --network host \
  -e PYTHONPATH=/app/implementation \
  -v /opt/jason/services/kfs:/runner:ro \
  -v /opt/jason/services/kfs:/collector:ro \
  -v /opt/jason/bootstrap/secrets/openbao/kyocera-kfs-read-approle:/secrets:ro \
  -v /var/lib/jason/runtime-secrets/kfs:/dbsecret:ro \
  -v /var/lib/jason/evidence/kfs-runs:/out:rw \
  "$JASON_KFS_RUNTIME_IMAGE" \
  python3 /runner/container_run_kfs.py
