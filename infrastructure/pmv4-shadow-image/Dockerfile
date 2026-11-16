# A1 source-only isolated OCI image. Built offline from the reviewed local base.
ARG BASE_IMAGE=openclaw:local
FROM ${BASE_IMAGE}
LABEL com.aot.jason.component="pmv4-shadow" \
      com.aot.jason.lifecycle="preproduction-only" \
      com.aot.jason.production-core="excluded" \
      com.aot.jason.provider-mutations="disabled"
# The A0 root-owned Compose uses command: [gateway, ...]. Its existing base
# ENTRYPOINT is only tini, which would incorrectly execute 'gateway' as a
# binary. Bind the CLI launcher here instead of changing A0 root controls.
ENTRYPOINT ["tini","-s","--","node","openclaw.mjs"]
CMD ["gateway"]
