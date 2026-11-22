# Exact licensed Owner plus one audit issuer on installed MCP LKG.
# Two Python payload files only; original 37 tools, service identities, and
# sidecar mounts stay unchanged. Never automatically promotes production.
ARG BASE_IMAGE=jason-mcp:base-pinned-b2f74bf15135
FROM ${BASE_IMAGE}
ARG REVIEWED_SOURCE_SHA
USER root
LABEL com.teamaot.jason.scope="licensed-owner-plus-audit-issuer-only"
LABEL com.teamaot.jason.source="${REVIEWED_SOURCE_SHA}"
LABEL com.teamaot.jason.base_image="sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
COPY --chown=0:0 implementation/mcp_service/src/jason_mcp/server.py /usr/local/lib/python3.12/site-packages/jason_mcp/server.py
COPY --chown=0:0 implementation/mcp_service/src/jason_mcp/audit_journal_adoption_approval.py /usr/local/lib/python3.12/site-packages/jason_mcp/audit_journal_adoption_approval.py
RUN chmod 0444 /usr/local/lib/python3.12/site-packages/jason_mcp/server.py /usr/local/lib/python3.12/site-packages/jason_mcp/audit_journal_adoption_approval.py
USER 1000:1000
CMD ["jason-mcp"]
