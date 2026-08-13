# Multi-stage Dockerfile for Loom API and Sandbox Worker
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    postgresql-client \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .
COPY loom/ loom/
COPY scripts/ scripts/

RUN pip install --upgrade pip && \
    pip install .

RUN useradd -m -u 10001 loomuser && \
    chown -R loomuser:loomuser /app

USER loomuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "loom.runtime.entrypoint"]
