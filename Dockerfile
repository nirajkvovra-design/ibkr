# Base stage: Use official lightweight Python 3.12 slim
FROM python:3.12-slim AS base

# System level optimizations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PATH="/app/.venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager for fast, secure, reproducible builds
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependencies manifest
COPY requirements.txt .

# Install dependencies using uv directly into the system python env (within docker boundary)
RUN uv pip install --system --no-cache -r requirements.txt

# Copy platform source files
COPY . .

# Configure a secure non-root user for executing live-trading infrastructure
RUN groupadd -r trading && useradd -r -g trading -u 1000 trading \
    && mkdir -p /app/logs && chown -R trading:trading /app

# Switch to the non-root operator
USER trading

# Default expose port for dashboard/API if applicable
EXPOSE 8000

# Default runtime command
CMD ["python", "trading_engine.py"]
