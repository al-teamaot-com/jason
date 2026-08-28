FROM node:24-bookworm-slim

WORKDIR /app

COPY infrastructure/jason-teams-gateway/package.json ./package.json
RUN npm install --omit=dev --no-audit --no-fund

COPY infrastructure/jason-teams-gateway/index.mjs ./index.mjs
COPY infrastructure/openclaw-jason-bridge/bridge-core.mjs ./bridge-core.mjs

ENV NODE_ENV=production
ENV PORT=3979

EXPOSE 3979

USER node

CMD ["node", "index.mjs"]
