# Independent SharePoint site-control image. Supply a reviewed immutable
# Jason runtime base digest at build time; never pull floating production tags.
ARG JASON_RUNTIME_BASE_IMAGE=python:3.12-slim
FROM ${JASON_RUNTIME_BASE_IMAGE}
USER root
COPY implementation/connectors/microsoft_graph /app/implementation/connectors/microsoft_graph
COPY implementation/connectors/core/openbao_secrets.py /app/implementation/connectors/core/openbao_secrets.py
COPY implementation/runtime_service/src/jason_runtime/microsoft_sharepoint.py /app/implementation/runtime_service/src/jason_runtime/microsoft_sharepoint.py
COPY tools/sharepoint_site_access_service.py /app/tools/sharepoint_site_access_service.py
RUN mkdir -p /var/lib/jason/sharepoint && chown 1000:1000 /var/lib/jason/sharepoint && chown -R 0:1000 /app/implementation/connectors/microsoft_graph /app/implementation/runtime_service/src/jason_runtime/microsoft_sharepoint.py /app/tools/sharepoint_site_access_service.py /app/implementation/connectors/core/openbao_secrets.py && chmod -R go-w,g+rX /app/implementation/connectors/microsoft_graph /app/implementation/runtime_service/src/jason_runtime/microsoft_sharepoint.py /app/tools/sharepoint_site_access_service.py /app/implementation/connectors/core/openbao_secrets.py
USER 1000:1000
CMD ["python", "/app/tools/sharepoint_site_access_service.py", "serve"]
