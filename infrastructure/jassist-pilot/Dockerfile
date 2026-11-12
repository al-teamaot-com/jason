# Isolated source-only J-Assist pilot image. Receives no screenshots by default.
# Before governed deployment, pin the base by digest and review full dependency lock.
ARG PYTHON_BASE=python:3.12-slim-bookworm
FROM ${PYTHON_BASE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv
RUN groupadd --gid 10001 jassist && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin jassist
COPY infrastructure/jassist-pilot/requirements.pilot.txt /srv/requirements.pilot.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /srv/requirements.pilot.txt && python -m pip check
COPY implementation/jassist /srv/jassist
COPY infrastructure/jassist-pilot/disabled_app.py /srv/disabled_app.py
RUN chmod -R a+rX /srv
USER 10001:10001
EXPOSE 3981
CMD ["python","-m","uvicorn","disabled_app:app","--host","0.0.0.0","--port","3981","--workers","1","--no-access-log","--no-proxy-headers"]
