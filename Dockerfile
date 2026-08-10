# Multi-stage Dockerfile for Loom Harness API Server
FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY loom/ ./loom/

RUN pip install --no-cache-dir build && pip install --no-cache-dir .

FROM python:3.11-slim as runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY loom/ ./loom/

RUN groupadd -g 1000 appgroup && useradd -u 1000 -g appgroup -m appuser && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["loom", "server", "--host", "0.0.0.0", "--port", "8000"]
