# Add exactly one Owner audit-archive approval tool to the unchanged
# production MCP LKG image. Never promote the whole unrelated Main source.
ARG BASE_IMAGE=jason-mcp:base-pinned-b2f74bf15135
FROM ${BASE_IMAGE}
USER root
ARG AUDIT_OVERLAY_MAIN_SHA
LABEL com.teamaot.jason.audit_overlay_purpose="one-use-owner-archive-adoption"
LABEL com.teamaot.jason.audit_overlay_reviewed_main_sha="${AUDIT_OVERLAY_MAIN_SHA}"
LABEL com.teamaot.jason.audit_overlay_base_image_sha256="b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
COPY --chown=0:0 infrastructure/jason-audit-journal-owner-executor/mcp_overlay.py /opt/jason-src/mcp_overlay.py
COPY --chown=0:0 implementation/mcp_service/src/jason_mcp/audit_journal_adoption_approval.py /opt/jason-src/audit_journal_adoption_approval_overlay.py
RUN chmod 0444 /opt/jason-src/mcp_overlay.py /opt/jason-src/audit_journal_adoption_approval_overlay.py \
    && python -m pip check
USER 1000:1000
CMD ["python","/opt/jason-src/mcp_overlay.py"]
