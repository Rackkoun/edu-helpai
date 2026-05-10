#!/usr/bin/env bash
# k8s/scripts/linux/minikube-start.sh

set -euo pipefail

GPU_MODE=false
[[ "${1:-}" == "--gpu" ]] && GPU_MODE=true

NAMESPACE="edu-helpai"
echo "🚀 Starting Edu-HelpAI on minikube (GPU=$GPU_MODE)..."

# -------------------------
# Step 1: Start minikube
# -------------------------
echo "1/6 — Starting minikube..."
if $GPU_MODE; then
    # Verify NVIDIA docker runtime is available on Linux host
    if ! docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi &>/dev/null; then
        echo "❌ GPU mode requires NVIDIA Container Toolkit."
        echo "   Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        exit 1
    fi
    minikube start --cpus 4 --memory 8192 --gpus all --driver docker
else
    minikube start --cpus 4 --memory 8192
fi

# Verify GPU visible to K8s
if $GPU_MODE; then
    sleep 5
    GPU_COUNT=$(kubectl get node minikube -o jsonpath='{.status.allocatable.nvidia\.com/gpu}' 2>/dev/null || true)
    if [[ -z "$GPU_COUNT" || "$GPU_COUNT" == "0" ]]; then
        echo "❌ Minikube node does not expose GPUs to Kubernetes."
        exit 1
    fi
    echo "✅ GPUs available to cluster: $GPU_COUNT"
fi

# ----------------------------------------------------
# Step 2: Build images inside minikube Docker daemon
# ----------------------------------------------------
echo "2/6 — Building images..."
eval "$(minikube docker-env)"
docker build -f docker/Dockerfile.backend -t edu-helpai-backend:latest .
docker build -f docker/Dockerfile.frontend -t edu-helpai-frontend:latest .
docker build -f docker/Dockerfile.mlflow -t edu-helpai-mlflow:latest .

# -----------------------------------
# Step 3: Create namespace + secrets
# -----------------------------------
echo "3/6 — Creating namespace and secrets..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml

kubectl create secret generic edu-secrets \
    --namespace edu-helpai \
    --from-literal=SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
    --dry-run=client -o yaml | kubectl apply -f -

# -----------------------
# Step 4: Deploy Ollama
# -----------------------
echo "4/6 — Deploying Ollama..."
if $GPU_MODE; then
    kubectl delete deployment ollama -n edu-helpai --ignore-not-found=true
    sleep 5
    echo "   Deploying NVIDIA device plugin..."
    kubectl apply -f k8s/nvidia-device-plugin.yaml
    sleep 5
    kubectl apply -f k8s/ollama-gpu-deployment.yaml
else
    kubectl delete deployment ollama-gpu -n edu-helpai --ignore-not-found=true
    sleep 5
    kubectl apply -f k8s/ollama-deployment.yaml
fi

echo "   Waiting for Ollama pod to be ready..."
kubectl wait --for=condition=ready pod -l app=ollama -n edu-helpai --timeout=300s

OLLAMA_POD=$(kubectl get pod -n edu-helpai -l app=ollama -o jsonpath='{.items[0].metadata.name}')
echo "   Pulling mistral:7b..."
kubectl exec -n edu-helpai "$OLLAMA_POD" -- ollama pull mistral:7b
echo "   Pulling nomic-embed-text..."
kubectl exec -n edu-helpai "$OLLAMA_POD" -- ollama pull nomic-embed-text

# -----------------------------------
# Step 5: Deploy backend + frontend + mlflow
# -----------------------------------
echo "5/6 — Deploying backend, frontend and MLflow..."
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/mlflow-deployment.yaml

echo "   Waiting for backend to be ready..."
kubectl wait --for=condition=ready pod -l app=backend -n edu-helpai --timeout=300s

# ---------------------------
# Step 6: Print access URLs
# ---------------------------
echo "6/6 — Done!"
echo ""
echo "════════════════════════════════════════════"
echo "✅ Edu-HelpAI running on minikube!"
echo ""
echo "  Access services:"
echo "  minikube service frontend-service -n edu-helpai --url"
echo "  minikube service backend-service  -n edu-helpai --url"
echo "  minikube service mlflow-service   -n edu-helpai --url"
echo ""
echo "  Or port-forward:"
echo "  kubectl port-forward -n edu-helpai svc/frontend-service 8001:8001"
echo "  kubectl port-forward -n edu-helpai svc/backend-service  8000:8000"
echo "  kubectl port-forward -n edu-helpai svc/mlflow-service   5000:5000"
echo "════════════════════════════════════════════"