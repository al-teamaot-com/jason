ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root

WORKDIR /opt/jason-src

COPY implementation /opt/jason-src/implementation

RUN chmod -R a+rX /opt/jason-src/implementation

ENV PYTHONPATH=/opt/jason-src/implementation/runtime_service/src:/opt/jason-src/implementation:/opt/jason-src/implementation/connectors/openclaw/src:/opt/jason-src/implementation/cap-007/src

COPY implementation/mcp_service/pyproject.toml /tmp/jason-mcp/pyproject.toml
COPY implementation/mcp_service/constraints-proven-pilot.txt /tmp/jason-mcp/constraints-proven-pilot.txt
COPY implementation/mcp_service/src /tmp/jason-mcp/src

RUN pip install --no-cache-dir \
    --constraint /tmp/jason-mcp/constraints-proven-pilot.txt \
    /tmp/jason-mcp

USER 1000:1000

EXPOSE 8000

CMD ["jason-mcp"]
