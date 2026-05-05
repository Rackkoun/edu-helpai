#!/usr/bin/env bash
# file k8s/scripts/linux/minikube-start.sh

# Full minikube startup automation mirroring scripts/start.sh

# Before usage ensure: chmod +x k8s/scripts/linux/minikube-start.sh
# Usage:
#   ./k8s/scripts/linux/minikube-start.sh           # CPU
#   ./k8s/scripts/linux/minikube-start.sh --gpu     # GPU

set -euo pipefail

GPU_MODE=false
[[ "${1:-}" == "--gpu" ]] && GPU_MODE=true

echo "🚀 Starting Edu-HelpAI on minikube..."


# -------------------------
# Step 1: Start minikube
# -------------------------
echo "1/6 — Starting minikube..."
minikube start --cpus 4 --memory 8192


# ----------------------------------------------------
# Step 2: Build images inside minikube Docker daemon
# ----------------------------------------------------
echo "2/6 — Building images..."
eval "$(minikube docker-env)"
docker build -f docker/Dockerfile.backend -t edu-helpai-backend:latest .
docker build -f docker/Dockerfile.frontend -t edu-helpai-frontend:latest .


# -----------------------------------
# Step 3: Create namespace + secret
# -----------------------------------
echo "3/6 — Creating namespace and secrets..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml

# Create SECRET_KEY imperatively, never from a committed YAML
kubectl create secret generic edu-secrets \
    --namespace edu-helpai \
    --from-literal=SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
    --dry-run=client -o yaml | kubectl apply -f -


# -----------------------
# Step 4: Deploy Ollama
# -----------------------
echo "4/6 — Deploying Ollama..."
if $GPU_MODE; then
    kubectl apply -f k8s/ollama-gpu-deployment.yaml
    # Point service to gpu deployment
    kubectl patch service ollama-service -n edu-helpai \
        -p '{"spec":{"selector":{"app":"ollama-gpu"}}}'
else
    kubectl apply -f k8s/ollama-deployment.yaml
fi

echo "   Waiting for Ollama pod to be ready..."
kubectl wait --for=condition=ready pod \
    -l app=ollama -n edu-helpai --timeout=120s

# Pull models inside the pod
OLLAMA_POD=$(kubectl get pod -n edu-helpai -l app=ollama -o jsonpath='{.items[0].metadata.name}')
echo "   Pulling mistral:7b (this takes a few minutes)..."
kubectl exec -n edu-helpai "$OLLAMA_POD" -- ollama pull mistral:7b
echo "   Pulling nomic-embed-text..."
kubectl exec -n edu-helpai "$OLLAMA_POD" -- ollama pull nomic-embed-text


# -----------------------------------
# Step 5: Deploy backend + frontend
# -----------------------------------
echo "5/6 — Deploying backend and frontend..."
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml

kubectl wait --for=condition=ready pod \
    -l app=backend -n edu-helpai --timeout=90s


# ---------------------------
# Step 6: Print access URLs
# ---------------------------
echo "6/6 — Done!"
echo ""
echo "════════════════════════════════════════════"
echo "✅ Edu-HelpAI running on minikube!"
echo ""
echo "  Run these to get URLs:"
echo "  minikube service frontend-service -n edu-helpai --url"
echo "  minikube service backend-service -n edu-helpai --url"
echo "════════════════════════════════════════════"