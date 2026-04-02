FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        antiword \
        build-essential \
        curl \
        ffmpeg \
        git \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirement.txt /app/backend/requirement.txt

RUN pip install --upgrade pip setuptools wheel uv \
    && pip install -r /app/backend/requirement.txt

COPY backend /app/backend

RUN mkdir -p /app/cache/tribev2 /app/data

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
