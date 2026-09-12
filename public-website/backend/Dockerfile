# ═══════════════════════════════════════════════════════════════════════════════
# RiskIntel Public Website Backend — Dockerfile
# Multi-stage build for minimal, secure production image
# ═══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first for layer caching
COPY requirements.txt .

# Install into a prefix for easy copy to runtime stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home --shell /bin/false appuser

# Install only runtime OS dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/
# Alembic is retained as a mirror of the Prisma schema for environments that
# provision with it. It is NOT run on deploy: Prisma owns the schema.
COPY alembic/ ./alembic/
COPY alembic.ini .

# Fix ownership
RUN chown -R appuser:appgroup /app

USER appuser

# Expose port
EXPOSE 8080

# Health check (uses /health/live endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health/live || exit 1

# ── Runtime configuration ─────────────────────────────────────────────────────
# Worker count is a deployment decision, not an image decision: a 512 MB
# container and an 8-core host want very different numbers, and four Python
# processes will not fit in the smaller one.
ENV WEB_CONCURRENCY=2

# `--forwarded-allow-ips` is deliberately NOT "*". Accepting X-Forwarded-For
# from anyone lets a client dictate the address the rate limiter counts against,
# which defeats it entirely. Only the reverse proxy in front is trusted, and it
# is named at deploy time.
ENV FORWARDED_ALLOW_IPS=127.0.0.1

# Shell form so the variables above expand; `exec` keeps uvicorn as PID 1 so it
# still receives the signals the orchestrator sends.
CMD exec uvicorn app.main:app     --host 0.0.0.0     --port 8080     --workers "$WEB_CONCURRENCY"     --no-access-log     --proxy-headers     --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
