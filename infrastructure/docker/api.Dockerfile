# ENSO Shield API image.
# Build context: repository root (see compose.yaml).
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/services/api/src

WORKDIR /app

COPY services/api/pyproject.toml services/api/README.md ./services/api/
COPY services/api/src ./services/api/src
RUN pip install ./services/api
COPY ml ./ml
COPY data ./data
COPY models ./models
COPY reports ./reports
COPY infrastructure/database ./infrastructure/database
COPY assets ./assets

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home enso \
    && chown -R enso:enso /app/data /app/models /app/reports

USER enso

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "enso_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]

