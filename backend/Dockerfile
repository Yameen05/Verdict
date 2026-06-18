# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user -r requirements.txt

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/verdict/.local/bin:$PATH" \
    PYTHONPATH=/app

# Non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 verdict

# curl for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the user-installed deps from the builder
COPY --from=builder --chown=verdict:verdict /root/.local /home/verdict/.local

COPY --chown=verdict:verdict . .

# Persistent SQLite directory
RUN mkdir -p /app/data && chown verdict:verdict /app/data

USER verdict

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Production server: gunicorn supervises uvicorn workers.
CMD ["gunicorn", "app.main:app", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "180"]
