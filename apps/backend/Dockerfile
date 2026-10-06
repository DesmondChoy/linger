FROM ghcr.io/astral-sh/uv:0.9.26-python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# The API imports both application adapters and the shared Linger runtime.
# Corpus artifacts and agent skills are runtime data, not build-only inputs.
COPY apps/backend apps/backend
COPY src src
COPY data/corpus data/corpus
RUN uv sync --frozen --no-dev

RUN groupadd --system linger \
    && useradd --system --gid linger --home-dir /app linger \
    && mkdir -p /app/state /app/memories /app/tmp/logs \
    && chown -R linger:linger /app/state /app/memories /app/tmp

USER linger

EXPOSE 8000

CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
