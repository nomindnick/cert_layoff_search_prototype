# Dockerfile — single FastAPI service for Railway.
# Builds the Vite SPA, installs BM25-only backend deps (no torch), then runs uvicorn.
# Indexes / records / metadata are pulled from Cloudflare R2 at startup (ephemeral fs).
FROM python:3.12-slim

# --- Node 20 (for the frontend build) ---
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps (cached layer) ---
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Frontend build (cache npm install on lockfile) ---
COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm ci
COPY frontend/ frontend/
RUN cd frontend && npm run build

# --- Backend source ---
COPY backend/ backend/

# Railway injects PORT; default to 8000 for local `docker run`.
ENV PORT=8000 \
    ENV=production \
    PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
