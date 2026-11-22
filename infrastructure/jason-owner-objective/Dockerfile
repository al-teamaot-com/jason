ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
LABEL com.teamaot.jason.component="owner-objective"
USER 0:0
COPY implementation /app/implementation
COPY tools /app/tools
ENV PYTHONPATH=/app:/app/tools:/app/implementation:/app/implementation/runtime_service/src:/app/implementation/connectors/openclaw/src:/app/implementation/cap-007/src
ENV PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
WORKDIR /app
EXPOSE 8097
HEALTHCHECK --interval=15s --timeout=4s --start-period=15s --retries=3 CMD python3 -B -c "import urllib.request;assert urllib.request.urlopen('http://127.0.0.1:8097/health',timeout=3).status==200"
ENTRYPOINT ["python3","-B","-m","jason_runtime.owner_objective_service"]
