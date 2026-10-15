# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.13.16-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints.txt ./
RUN pip install --user -r requirements.txt

# ---------- runtime ----------
FROM python:3.13.16-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/verdict/.local/bin:$PATH" \
    PYTHONPATH=/app

# Non-root user
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 verdict

# Upgrade the base OS and remove build-only package tooling from the runtime.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip

WORKDIR /app

# Copy the user-installed deps from the builder
COPY --from=builder --chown=verdict:verdict /root/.local /home/verdict/.local

COPY --chown=verdict:verdict . .

# Persistent SQLite directory
RUN mkdir -p /app/data && chown verdict:verdict /app/data

USER verdict

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" || exit 1

# One worker is the safe default while rate limits use in-process storage and
# SQLite is supported. Scale out only after configuring shared infrastructure.
#
# No --forwarded-allow-ips: with it set to "*" uvicorn overwrites the peer
# address with the leftmost X-Forwarded-For entry, which the client controls, so
# every per-IP rate limit becomes trivially bypassable. The app resolves the
# client address itself against TRUSTED_PROXY_IPS — see app/netaddr.py.
CMD ["gunicorn", "app.main:app", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", \
     "--access-logformat", "%(h)s %(m)s %(U)s %(s)s %(L)s", \
     "--forwarded-allow-ips", "", \
     "--umask", "0077", \
     "--error-logfile", "-", \
     "--timeout", "180"]
