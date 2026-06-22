#!/usr/bin/env bash
# build.sh — install backend deps and build the frontend SPA.
# This is the deploy/CI build step. The OFFLINE index build lives in build/ and is run
# separately on the desktop (see README "Offline build").
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Installing backend dependencies"
pip install --no-cache-dir -r requirements.txt

echo "==> Building frontend"
cd frontend
npm ci
npm run build

echo "==> Build complete (frontend/dist ready, backend deps installed)"
