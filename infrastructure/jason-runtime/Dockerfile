FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/implementation:/app/implementation/connectors/openclaw/src:/app/implementation/runtime_service/src

WORKDIR /app

COPY implementation /app/implementation

RUN python -m pip install --no-cache-dir \
      /app/implementation \
      /app/implementation/connectors/openclaw \
      /app/implementation/runtime_service

USER 1000:1000

EXPOSE 8080

CMD ["python", "-m", "jason_runtime.main"]
