# k8s/scripts/windows/Start-Minikube.ps1
#
# Full minikube startup automation for Edu-HelpAI on Windows.
# Usage:
#   .\k8s\scripts\Start-Minikube.ps1          # CPU
#   .\k8s\scripts\Start-Minikube.ps1 -Gpu     # NVIDIA GPU
#
# Requirements:
#   - minikube
#   - kubectl
#   - Docker Desktop (WSL2 backend)
#   - Python 3.11 (for secret generation)

param(
    [switch]$Gpu,
    [int]$PodTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Namespace = "edu-helpai"

# ----------------
# Helpers
# ----------------
function Write-Step    { param([string]$Message) Write-Host ""; Write-Host $Message -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Fail    { param([string]$Message) Write-Host $Message -ForegroundColor Red }


function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Fail "$Name not found. $InstallHint"
        exit 1
    }
}

function Invoke-Kubectl {
    param([string[]]$Arguments)
    kubectl @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "kubectl command failed: kubectl $($Arguments -join ' ')"
        exit $LASTEXITCODE
    }
}

function Wait-PodReady {
    param([string]$Label)
    Write-Host "  Waiting for pod ($Label) to be ready..." -NoNewline

    # Wait for pod to even exist first (up to 60s)
    $elapsed = 0
    while ($elapsed -lt 60) {
        $count = kubectl get pod -l $Label -n $Namespace --no-headers 2>$null | Measure-Object -Line
        if ($count.Lines -gt 0) { break }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 5
        $elapsed += 5
    }

    kubectl wait --for=condition=ready pod `
        -l $Label `
        -n $Namespace `
        --timeout="${PodTimeoutSeconds}s"

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Fail "Pod $Label did not become ready within ${PodTimeoutSeconds}s"
        Write-Host "  Describe:"
        kubectl describe pod -l $Label -n $Namespace
        exit 1
    }
    Write-Host " OK" -ForegroundColor Green
}

# ----------------------
# Preflight checks
# ----------------------
Write-Step "Checking prerequisites..."
Assert-Command "minikube"  "Install from https://minikube.sigs.k8s.io/docs/start/"
Assert-Command "kubectl"   "Install from https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/"
Assert-Command "docker"    "Install Docker Desktop from https://docs.docker.com/desktop/windows/"
Assert-Command "python"    "Install Python 3.11 from https://python.org"
Write-Success "  All prerequisites found"

if ($Gpu) {
    Write-Host "  GPU mode enabled (NVIDIA)" -ForegroundColor Yellow
} else {
    Write-Host "  CPU mode (pass -Gpu for NVIDIA GPU)" -ForegroundColor Gray
}

# ----------------------------
# Step 1: Start minikube
# ----------------------------
Write-Step "Step 1/6 - Starting minikube..."
minikube start --cpus 4 --memory 8192
if ($LASTEXITCODE -ne 0) { Write-Fail "minikube start failed"; exit 1 }
Write-Success "  minikube started"


# -----------------------------------------------------
# Step 2: Build images inside minikube Docker daemon
# -----------------------------------------------------
Write-Step "Step 2/6 - Building images inside minikube..."

# Capture minikube docker-env and apply it to current session
$envVars = minikube docker-env --shell=cmd 2>$null
foreach ($line in $envVars) {
    if ($line -match '^SET (\w+)=(.+)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
    }
}

docker build -f docker/Dockerfile.backend  -t edu-helpai-backend:latest  .
if ($LASTEXITCODE -ne 0) { Write-Fail "Backend image build failed"; exit 1 }

docker build -f docker/Dockerfile.frontend -t edu-helpai-frontend:latest .
if ($LASTEXITCODE -ne 0) { Write-Fail "Frontend image build failed"; exit 1 }
Write-Success "  Images built inside minikube"

# ----------------------------------------
# Step 3: Apply namespace, config, PVCs
# ----------------------------------------
Write-Step "Step 3/6 - Creating namespace, config, storage..."
Invoke-Kubectl @("apply", "-f", "k8s/namespace.yaml")
Write-Host "  Waiting for namespace to become Active..." -NoNewline
for ($i = 0; $i -lt 12; $i++) {
    $phase = kubectl get namespace $Namespace -o jsonpath='{.status.phase}' 2>$null
    if ($phase -eq "Active") { Write-Host " OK" -ForegroundColor Green; break }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 2
    if ($i -eq 11) { Write-Fail "Namespace never became Active"; exit 1 }
}

Invoke-Kubectl @("apply", "-f", "k8s/configmap.yaml")
Invoke-Kubectl @("apply", "-f", "k8s/pvc.yaml")

# Generate a secure SECRET_KEY and apply as a K8s Secret
$secretKey = python -c "import secrets; print(secrets.token_hex(32))"
if (-not $secretKey -or $secretKey.Length -lt 32) {
    Write-Fail "Failed to generate SECRET_KEY"
    exit 1
}

# Use --dry-run + apply to be idempotent
kubectl create secret generic edu-secrets `
    --namespace $Namespace `
    --from-literal="SECRET_KEY=$secretKey" `
    --dry-run=client -o yaml | kubectl apply -f -

if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create secret"; exit 1 }
Write-Success "  Namespace, config and secrets applied"

# ---------------------------------------
# Step 4: Deploy Ollama + pull models
# ---------------------------------------
Write-Step "Step 4/6 - Deploying Ollama..."
if ($Gpu) {
    Invoke-Kubectl @("apply", "-f", "k8s/ollama-gpu-deployment.yaml")
    Invoke-Kubectl @("patch", "service", "ollama-service",
        "-n", $Namespace,
        "-p", '{"spec":{"selector":{"app":"ollama-gpu"}}}')
} else {
    Invoke-Kubectl @("apply", "-f", "k8s/ollama-deployment.yaml")
}

Wait-PodReady -Label "app=ollama"

# Get pod name and pull models
$ollamaPod = kubectl get pod -n $Namespace -l app=ollama `
    -o jsonpath='{.items[0].metadata.name}'

Write-Host "  Pulling mistral:7b (takes a few minutes)..."
kubectl exec -n $Namespace $ollamaPod -- ollama pull mistral:7b

Write-Host "  Pulling nomic-embed-text..."
kubectl exec -n $Namespace $ollamaPod -- ollama pull nomic-embed-text

Write-Success "  Ollama ready with models"

# -------------------------------------
# Step 5: Deploy backend + frontend
# -------------------------------------
Write-Step "Step 5/6 - Deploying backend and frontend..."
Invoke-Kubectl @("apply", "-f", "k8s/backend-deployment.yaml")
Invoke-Kubectl @("apply", "-f", "k8s/frontend-deployment.yaml")
Wait-PodReady -Label "app=backend"
Write-Success "  Backend and frontend deployed"


# ----------------------------
# Step 6: Print access info
# ----------------------------
Write-Step "Step 6/6 - Access"
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Success "  Edu-HelpAI is running on minikube!"
Write-Host "  Open services:"
Write-Host "  minikube service frontend-service -n $Namespace" -ForegroundColor Yellow
Write-Host "  minikube service backend-service  -n $Namespace" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Or port-forward:"
Write-Host "  kubectl port-forward svc/frontend-service 8001:8001 -n $Namespace" -ForegroundColor Yellow
Write-Host "  kubectl port-forward svc/backend-service  8000:8000 -n $Namespace" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Green