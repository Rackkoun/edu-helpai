#!/usr/bin/env bash
# file k8s/scripts/linux/minikube-connect.sh
# Forwards all Edu-HelpAI services to localhost. Ctrl+C stops everything.
# make this script exec: chmod +x k8s/scripts/linux/minikube-connect.sh
set -euo pipefail
NAMESPACE="${1:-edu-helpai}"

cleanup() {
    echo ""
    echo "Stopping port-forwards..."
    kill "${PIDS[@]}" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "Done."
}
trap cleanup INT TERM EXIT

PIDS=()

kubectl port-forward svc/frontend-service 8001:8001 -n "$NAMESPACE" &
PIDS+=($!)
kubectl port-forward svc/backend-service  8000:8000 -n "$NAMESPACE" &
PIDS+=($!)
kubectl port-forward svc/mlflow-service   5000:5000  -n "$NAMESPACE" &
PIDS+=($!)
kubectl port-forward svc/ollama-service  11434:11434 -n "$NAMESPACE" &
PIDS+=($!)

echo ""
echo "============================================"
echo "  Chat UI      ->  http://localhost:8001"
echo "  API docs     ->  http://localhost:8000/docs"
echo "  MLflow Logs  ->  http://localhost:5000"
echo "  Ollama       ->  http://localhost:11434"
echo "  Press Ctrl+C to stop."
echo "============================================"

wait