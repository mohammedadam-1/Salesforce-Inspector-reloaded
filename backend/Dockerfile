FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir "celery[redis]" && \
    rm -rf /root/.cache/pip

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        curl && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 -r app && \
    useradd -u 1000 -r -g app -d /app -s /bin/false app

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/
COPY pyproject.toml .

RUN chown -R app:app /app

USER app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/api/v1/health/live || exit 1

EXPOSE 8000

CMD ["uvicorn", "sfir_backend.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
