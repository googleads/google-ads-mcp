FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=8000

WORKDIR /app

# ---------------------------------------------------------------
# Phase 1: install third-party dependencies
# ---------------------------------------------------------------
# Cached as long as pyproject.toml doesn't change, so day-to-day
# code edits rebuild in seconds. Deps are extracted at build time
# via tomllib (stdlib on Python 3.11+) so pyproject.toml stays the
# single source of truth — no separate requirements.txt to sync.
#
# build-essential is kept only inside this RUN: grpcio ships
# wheels for linux/amd64 and linux/arm64, but we purge the toolchain
# before committing the layer so it's still a fallback, not a cost.
COPY pyproject.toml ./
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && python -c "import tomllib; \
               deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; \
               open('/tmp/requirements.txt','w').write('\n'.join(deps))" \
 && pip install -r /tmp/requirements.txt \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/* /tmp/requirements.txt

# ---------------------------------------------------------------
# Phase 2: install the local package
# ---------------------------------------------------------------
# This layer rebuilds whenever any Python source (or README /
# MANIFEST.in, which setuptools uses at package build time) changes.
# --no-deps skips the whole transitive dep tree since Phase 1 already
# installed them, so this step is ~2-5s even on a cold builder.
COPY README.md MANIFEST.in ./
COPY ads_mcp ./ads_mcp
RUN pip install --no-deps .

EXPOSE 8000

# FastMCP opens the port immediately on startup; if it isn't listening
# the container is genuinely broken.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1', 8000)); s.close()" || exit 1

CMD ["google-ads-mcp"]
