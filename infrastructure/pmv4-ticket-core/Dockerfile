ARG JASON_RUNTIME_DEPENDENCY_IMAGE=jason-runtime:production
FROM ${JASON_RUNTIME_DEPENDENCY_IMAGE} AS runtime-deps

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/implementation:/app/implementation/cap-007/src:/app/implementation/connectors/openclaw/src:/app/implementation/runtime_service/src

WORKDIR /app

# Reuse the exact reviewed runtime dependency set without network access.
# The final stage is a fresh Python base, so HTTP EXPOSE/CMD metadata is not
# inherited from the dependency image.
COPY --from=runtime-deps /usr/local /usr/local
COPY implementation /app/implementation
COPY config /app/config

RUN chown -R 0:1000 /app/implementation /app/config \
    && chmod -R go-w,g+rX /app/implementation /app/config

USER 1000:1000

# Deliberately no EXPOSE: Stage C is a non-HTTP worker.
CMD ["python", "-m", "jason_runtime.ticket_worker_service"]
