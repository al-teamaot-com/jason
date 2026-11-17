ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/implementation:/app/implementation/cap-007/src:/app/implementation/connectors/openclaw/src:/app/implementation/runtime_service/src

WORKDIR /app

COPY implementation /app/implementation
COPY config /app/config

RUN python -m pip install --no-cache-dir \
      /app/implementation \
      /app/implementation/connectors/openclaw \
      /app/implementation/runtime_service \
    && chown -R 0:1000 /app/implementation /app/config \
    && chmod -R go-w,g+rX /app/implementation /app/config

USER 1000:1000

# Deliberately no EXPOSE: Stage C is a non-HTTP worker.
CMD ["python", "-m", "jason_runtime.ticket_worker_service"]
