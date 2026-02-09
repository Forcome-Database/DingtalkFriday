#!/usr/bin/env bash
set -e

echo "============================================"
echo "  DingtalkFriday - Docker Production Deploy"
echo "============================================"
echo

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker not found. Please install Docker first."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "[ERROR] Docker Compose not found."
    exit 1
fi

# Check .env
if [ ! -f .env ]; then
    echo "[ERROR] .env not found in project root."
    echo "Please copy .env.example to .env and fill in config."
    exit 1
fi

# Read ports from .env
FRONTEND_PORT=$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2 | tr -d '[:space:]')
BACKEND_PORT=$(grep -E '^BACKEND_PORT=' .env | cut -d= -f2 | tr -d '[:space:]')
FRONTEND_PORT=${FRONTEND_PORT:-80}
BACKEND_PORT=${BACKEND_PORT:-8000}

mkdir -p backend/data

echo "[1/3] Stopping old containers..."
docker compose down

echo
echo "[2/3] Building and starting containers..."
docker compose up -d --build

echo
echo "[3/3] Waiting for services..."
sleep 5

if curl -sf "http://localhost:${BACKEND_PORT}/api/health" > /dev/null 2>&1; then
    echo "[OK] Backend is ready."
else
    echo "[INFO] Backend is still starting, please wait..."
fi

echo
echo "============================================"
echo "  Deploy complete!"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo "  Backend:  http://localhost:${BACKEND_PORT}/api/health"
echo "  Logs:     docker compose logs -f"
echo "  Stop:     docker compose down"
echo "============================================"
