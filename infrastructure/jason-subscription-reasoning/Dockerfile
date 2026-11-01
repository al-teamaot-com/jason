FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.166.0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CODEX_HOME=/var/lib/jason/codex

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && useradd --uid 1000 --gid 100 --create-home --home-dir /home/jason jason \
    && mkdir -p /app /var/lib/jason/codex \
    && chown -R 1000:100 /app /var/lib/jason/codex

COPY implementation/runtime_service/src/jason_runtime/subscription_reasoning_service.py /app/subscription_reasoning_service.py

USER 1000:100
WORKDIR /app

EXPOSE 8091

CMD ["python3", "/app/subscription_reasoning_service.py"]
