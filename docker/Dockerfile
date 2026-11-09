FROM python:3.15.2-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /home/app/.cache/embeddings \
    && chown -R app:app /home/app/.cache

COPY movies.json ./
COPY engine ./engine
COPY web ./web
COPY docker/scripts/wait_for_qdrant.py docker/scripts/healthcheck.py ./docker/scripts/
COPY docker/scripts/start-loader.sh docker/scripts/start-web.sh ./docker/scripts/

USER app
EXPOSE 18000
CMD ["/bin/sh", "docker/scripts/start-web.sh"]
