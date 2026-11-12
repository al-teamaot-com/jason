ARG BASE_IMAGE=jason-mcp:generic-governed-8f1e864947a2
FROM ${BASE_IMAGE}

USER root

WORKDIR /opt/jason-src

COPY implementation /opt/jason-src/implementation
# PMv4 Owner issuer reuses the existing signed-proof modules, not a second
# approval system. Only these reviewed, non-secret source libraries ship in
# the MCP image; actual signer/trust/manifest are host-provisioned separately.
COPY tools/pmv4_shadow_owner_issuer.py tools/pmv4_shadow_release.py /opt/jason-src/tools/

RUN chmod -R a+rX /opt/jason-src/implementation /opt/jason-src/tools

ENV PYTHONPATH=/opt/jason-src:/opt/jason-src/implementation/runtime_service/src:/opt/jason-src/implementation:/opt/jason-src/implementation/connectors/openclaw/src:/opt/jason-src/implementation/cap-007/src

COPY implementation/mcp_service/pyproject.toml /tmp/jason-mcp/pyproject.toml
COPY implementation/mcp_service/constraints-proven-pilot.txt /tmp/jason-mcp/constraints-proven-pilot.txt
COPY implementation/mcp_service/src /tmp/jason-mcp/src

RUN pip install --no-cache-dir \
    --constraint /tmp/jason-mcp/constraints-proven-pilot.txt \
    /tmp/jason-mcp

USER 1000:1000

EXPOSE 8000

CMD ["jason-mcp"]
