# Enterprise AI Platform — application image.
# Build from the repo root:  docker build -f docker/Dockerfile -t ai-platform .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# No system build deps needed — asyncpg / bcrypt / aiomysql ship wheels.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

# Entrypoint runs migrations (and optional seed) before serving.
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
