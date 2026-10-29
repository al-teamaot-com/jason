ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/implementation:/app/implementation/cap-007/src:/app/implementation/connectors/openclaw/src:/app/implementation/runtime_service/src

WORKDIR /app

COPY implementation /app/implementation
COPY config /app/config
# Ship only the reviewed disabled JSON v1 shadow document as image-owned data.
# The runtime cannot modify this document or gain authority from it.
COPY docs/playbooks/json/candidates/windows_time_source-0.1.0-jsonpreview.json /app/config/json-playbooks/windows_time_source-0.1.0-jsonpreview.json

# Release Manager checks out pinned source under restrictive 0077 permissions.
# Docker COPY preserves those modes and root ownership. Normalize the
# non-secret, build-time source to root:runtime-group and grant group read/
# traverse WITHOUT granting any runtime write access to executable code.
# Do this after pip install so generated package metadata is accessible too.
RUN python -m pip install --no-cache-dir \
      /app/implementation \
      /app/implementation/connectors/openclaw \
      /app/implementation/runtime_service \
    && chown -R 0:1000 /app/implementation /app/config \
    && chmod -R go-w,g+rX /app/implementation /app/config

USER 1000:1000

EXPOSE 8080

CMD ["python", "-m", "jason_runtime.main"]
