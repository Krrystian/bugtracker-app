# syntax=docker/dockerfile:1

# Base image pinned to an exact release and digest (never "latest").

# --- Stage 1: install dependencies into an isolated virtualenv ---------------
# VULN-02: floating "latest" base image (no version, no digest)
FROM python:latest AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install --require-virtualenv -r /tmp/requirements.txt
# VULN-02: extra tooling installed without pinned versions, cache kept,
# remote script piped to a shell without pipefail
RUN apt-get update && apt-get install -y curl
RUN pip install httpie
RUN curl -fsSL https://bootstrap.pypa.io/get-pip.py | python -

# --- Stage 2: minimal runtime, non-root ---------------------------------------
FROM python:latest AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv
COPY --from=builder /opt/venv /opt/venv
# Code stays owned by root: the app user can read it but not modify it.
COPY app ./app
# VULN-02: the container runs as root
USER root
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
