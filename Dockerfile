FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM node:22-bookworm-slim AS runtime

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip bash git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g openclaw

COPY . /app
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

RUN chmod +x /app/bin/*.sh

ENV OPENCLAW_DIR=/data/openclaw
ENV PORT=18890

EXPOSE 18890

CMD ["bash", "/app/bin/docker_bootstrap.sh"]
