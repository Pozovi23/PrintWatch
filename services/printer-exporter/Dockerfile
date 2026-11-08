# Stage 1: Build stage with uv
FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Copy workspace manifests and lockfile for caching
COPY pyproject.toml uv.lock ./
COPY services/printer-exporter/pyproject.toml ./services/printer-exporter/
COPY services/camera-proxy/pyproject.toml ./services/camera-proxy/

# Synchronize production dependencies for printer-exporter using uv.lock
RUN uv sync --frozen --no-dev --no-install-project --package printer-exporter


# Stage 2: Minimal runtime stage
FROM python:3.11-slim AS runtime

# Install curl for container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/false appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source code and tests
COPY --chown=appuser:appgroup services/printer-exporter/exporter/ /app/exporter/
COPY --chown=appuser:appgroup services/printer-exporter/tests/ /app/tests/

# Switch to non-root user
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 9108

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9108/healthz || exit 1

ENTRYPOINT ["python", "-m", "exporter.main"]
