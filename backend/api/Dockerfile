FROM python:3.15.2-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY backend/api/requirements.txt ./backend/api/requirements.txt
RUN python -m venv /opt/venv \
    && python -m pip install --no-cache-dir -r backend/api/requirements.txt \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /home/app/.cache/embeddings \
    && chown -R app:app /home/app/.cache

COPY backend ./backend

USER app
EXPOSE 18000
CMD ["/bin/sh", "backend/scripts/start-backend.sh"]
