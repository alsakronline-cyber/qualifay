FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# System dependencies (Playwright + psycopg2 + ffmpeg for voice-note transcoding)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev postgresql-client curl wget gnupg ffmpeg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# BuildKit cache mount: downloaded wheels persist across builds in a cache that lives
# OUTSIDE the image, so a requirements.txt change (or a build-cache prune) re-resolves
# from local wheels instead of re-downloading every package. --no-cache-dir is dropped
# because it would defeat the mount; the cache never lands in an image layer, so image
# size is unchanged.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Playwright Chromium for scraping (ARM64). Base image already has the shared libs,
# so install the browser only (no --with-deps, which fails on this ARM base). Do NOT
# swallow errors — a missing browser breaks the linkedin/facebook scrapers.
RUN playwright install chromium

COPY . .

RUN mkdir -p /app/media /app/logs

EXPOSE 5000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]
