#!/bin/bash
set -e

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    echo "GPU detected — starting with GPU acceleration"
    COMPOSE_PROFILE="gpu"
else
    echo "No GPU found — starting with CPU only"
    COMPOSE_PROFILE="cpu"
fi

echo "Building and starting containers..."
docker compose --profile $COMPOSE_PROFILE up --build -d

echo ""
echo "----------------------------------------"
echo "  Frontend:  http://localhost"
echo "  Swagger:   http://localhost:8000/docs"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana:    http://localhost:3000 (admin/admin)"
echo "----------------------------------------"