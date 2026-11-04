FROM python:3.15.2-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 app

COPY movies.json ./
COPY engine ./engine
COPY web ./web
COPY docker/wait_for_qdrant.py docker/healthcheck.py ./docker/

USER app
EXPOSE 5000
CMD ["python", "-m", "uvicorn", "web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "5000"]
