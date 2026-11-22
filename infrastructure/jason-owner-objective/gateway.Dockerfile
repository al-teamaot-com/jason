ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
LABEL com.teamaot.jason.objective-route="1"
COPY infrastructure/jason-teams-gateway/index.mjs /app/index.mjs
COPY infrastructure/jason-teams-gateway/objective-approval-route.mjs /app/objective-approval-route.mjs
