#!/bin/sh
set -eu

exec /usr/bin/docker run --rm --user 0:0 --network host \
  -e PYTHONPATH=/app/implementation \
  -v /home/al/jason-runtime-tools/kfs:/runner:ro \
  -v /home/al/jason-runtime-tools/kfs:/collector:ro \
  -v /opt/jason/bootstrap/secrets/openbao/kyocera-kfs-read-approle:/secrets:ro \
  -v /home/al/jason-secrets/kfs:/dbsecret:ro \
  -v /home/al/jason-evidence/kfs-runs:/out:rw \
  jason-runtime:local \
  python3 /runner/container_run_kfs.py
