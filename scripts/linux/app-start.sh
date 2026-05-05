#!/usr/bin/env bash

# file: scripts/linux/app-start.sh
# Full startup automation for Edu-HelpAI - Linux or Mac
# Usage:
# ./scripts/linux/app-start.sh   # CPU
# ./scripts/linux/app-start.sh --gpu   # GPU (NVIDIA)

# set exit on error, unser var, pipe failure
set -euo pipefail

# -----------------------------------
# CONFIG
# -----------------------------------
OLLAMA_MODELS=("mistral:7b" "nomic-embed-text")
COMPOSE_FILE="docker-compose.yaml"
MAX_HEALTH_WAIT=120  # seconds before giving up on a healthcheck

# -----------------------------------
# PARSE ARGS
# -----------------------------------
GPU_PROFILE=""
if [[ "${1:-}" == "--gpu" ]]; then
    GPU_PROFILE="--profile gpu"
    echo "🎮 GPU mode enabled (NVIDIA)"
else
    echo "💻 CPU mode (pass --gpu for NVIDIA)"
fi

COMPOSE="docker compose -f $COMPOSE_FILE $GPU_PROFILE"

# ------------------------------------
# HELPERS
# ------------------------------------
wait_healthy() {
    local container=$1
    local elapsed=0
    echo -n "⏳ Waiting for $container to become healthy..."
    until [[ "$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null)" == "healthy" ]]; do
        if (( elapsed >= MAX_HEALTH_WAIT )); then
            echo ""
            echo "❌ $container did not become healthy within ${MAX_HEALTH_WAIT}s"
            echo "    Check logs with: docker compose logs $container"
            exit 1
        fi
        echo -n "."
        sleep 5
        (( elapsed += 5 ))
    done
    echo " ✅"
}

# ----------------------------------------
# CONTAINERS
# ----------------------------------------

# Step 1: Build images
echo ""
echo "🔨 Step 1/5 — Building images..."
$COMPOSE build

# Step 2: Start Ollama
echo ""
echo "🦙 Step 2/5 — Starting Ollama..."
if [[ -n "$GPU_PROFILE" ]]; then
    $COMPOSE up ollama-gpu -d
else
    $COMPOSE up ollama -d
fi

wait_healthy "edu_ollama"

# Step 3: Pull models (skip if already present)
echo ""
echo "📦 Step 3/5 — Pulling models (skips if already downloaded)..."
for model in "${OLLAMA_MODELS[@]}"; do
    echo "   → $model"
    docker exec edu_ollama ollama pull "$model"
done
echo "✅ Models ready"

# Step 4: Start all remaining services
echo ""
echo "🚀 Step 4/5 — Starting backend, frontend, mlflow..."
$COMPOSE up -d

wait_healthy "edu_backend"

# Step 5: Print status
echo ""
echo "📊 Step 5/5 — Status"
$COMPOSE ps

echo ""
echo "════════════════════════════════════════════"
echo "✅ Edu-HelpAI is running!"
echo ""
echo "  🖥️  Chat UI   → http://localhost:8001"
echo "  ⚙️  API docs  → http://localhost:8000/docs"
echo "  📈 MLflow    → http://localhost:5000"
echo "════════════════════════════════════════════"