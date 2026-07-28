# syntax=docker/dockerfile:1
# Multi-stage & Cache-Optimized Dockerfile for Arm Federated AI Control Plane Gateway
FROM python:3.12-slim AS builder

WORKDIR /app

# 1. Install system utilities using APT cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.cargo/bin:$PATH"

# 2. Copy dependency manifests FIRST (pyproject.toml + uv.lock for deterministic installs)
COPY pyproject.toml uv.lock ./

# 3. Install production dependencies into virtual environment using uv sync
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ==============================================================================
# Production Runtime Stage
# ==============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy virtual environment from builder stage (Cached until lockfile changes)
COPY --from=builder /app/.venv /app/.venv

# Copy application source code LAST
COPY src /app/src
COPY config /app/config
COPY .platform /app/.platform

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "src.control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
