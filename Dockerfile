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

# 2. Copy dependency manifest FIRST (invalidates dependency layer ONLY when dependencies change)
COPY pyproject.toml ./

# 3. Install dependencies into virtual environment using UV cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install -r pyproject.toml

# ==============================================================================
# Production Runtime Stage
# ==============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy virtual environment from builder stage (Cached until pyproject.toml changes)
COPY --from=builder /app/.venv /app/.venv

# Copy application source code LAST (Ensures fast rebuilds when python files change)
COPY src /app/src
COPY config /app/config
COPY .platform /app/.platform

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "src.control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
