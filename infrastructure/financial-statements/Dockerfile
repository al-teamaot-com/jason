ARG JASON_COMPONENT_BASE=jason-runtime:release-d1b8c196dadd-bb7d28ebd5e5
FROM ${JASON_COMPONENT_BASE}
ARG JASON_SOURCE_REVISION
LABEL com.aot.jason.component="financial-statements" com.aot.jason.source_revision="${JASON_SOURCE_REVISION}"
USER 0:0
COPY implementation /app/implementation
RUN python -m pip install --no-cache-dir pypdf==6.1.3 && chown -R 0:1000 /app/implementation && chmod -R go-w,g+rX /app/implementation
USER 1000:1000
ENTRYPOINT ["python", "-m", "jason_runtime.financial_statement_process"]
CMD []
