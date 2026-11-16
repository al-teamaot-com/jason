# A1 source-only OCI image profile. Build offline from an existing pinned
# local OpenClaw image. This file itself grants no production authority.
ARG BASE_IMAGE=openclaw:local
FROM ${BASE_IMAGE}
LABEL com.aot.jason.component="pmv4-shadow" \
      com.aot.jason.lifecycle="preproduction-only" \
      com.aot.jason.production-core="excluded" \
      com.aot.jason.provider-mutations="disabled"
