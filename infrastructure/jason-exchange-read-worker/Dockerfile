FROM mcr.microsoft.com/powershell:7.4-ubuntu-22.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && pwsh -NoLogo -NoProfile -Command "Set-PSRepository -Name PSGallery -InstallationPolicy Trusted; Install-Module ExchangeOnlineManagement -RequiredVersion 3.10.1 -Scope AllUsers -Force"

ENV JASON_EXCHANGE_WORKER_HOST=0.0.0.0 \
    JASON_EXCHANGE_WORKER_PORT=8091 \
    JASON_EXCHANGE_CERTIFICATE_PFX=/run/jason-secrets/microsoft-exchange/certificate.pfx \
    JASON_EXCHANGE_CERTIFICATE_PASSWORD_FILE=/run/jason-secrets/microsoft-exchange/certificate-password \
    JASON_EXCHANGE_WORKER_TOKEN_FILE=/run/jason-secrets/microsoft-exchange/worker-token

WORKDIR /app
COPY infrastructure/jason-exchange-read-worker/worker.py /app/worker.py
COPY infrastructure/jason-exchange-read-worker/invoke_exchange_read.ps1 /app/invoke_exchange_read.ps1

RUN useradd --system --uid 10001 --user-group --create-home --shell /usr/sbin/nologin jason-worker \
    && chown -R jason-worker:jason-worker /app

USER 10001:10001

EXPOSE 8091

CMD ["python3", "/app/worker.py"]
