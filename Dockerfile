# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
RUN npm install --global pnpm@10.34.6
COPY apps/frontend/package.json apps/frontend/pnpm-lock.yaml ./apps/frontend/
RUN pnpm --dir apps/frontend install --frozen-lockfile
COPY apps/frontend ./apps/frontend
COPY packages/architecture-map ./packages/architecture-map
RUN pnpm --dir apps/frontend build

FROM ghcr.io/astral-sh/uv:0.8.3 AS uv
FROM ubuntu:24.04 AS runtime
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision=$VCS_REF
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.12-venv ca-certificates libstdc++6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/.venv/bin:$PATH \
    FASTEMBED_CACHE_PATH=/opt/linger/models \
    LINGER_STATE_DIR=/var/lib/linger \
    LINGER_MEMORY_DIR=/var/lib/linger/memories \
    LINGER_STATIC_DIR=/app/static
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY apps/backend ./apps/backend
COPY data/corpus ./data/corpus
COPY docker/cache_models.py ./docker/cache_models.py
RUN uv sync --locked --no-dev --no-editable \
    && python docker/cache_models.py \
    && chmod -R a+rX /opt/linger/models
COPY --from=frontend /build/apps/frontend/dist ./static
RUN groupadd --gid 10001 linger \
    && useradd --uid 10001 --gid linger --create-home linger \
    && mkdir -p /var/lib/linger /app/tmp/logs \
    && chown linger:linger /var/lib/linger /app/tmp/logs
ENV HF_HUB_OFFLINE=1
USER linger
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=8)"
CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
