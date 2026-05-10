# k8s/scripts/windows/Start-Minikube.ps1

param(
    [switch]$Gpu,
    [int]$PodTimeoutSeconds = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Namespace = "edu-helpai"

function Write-Step    { param([string]$Message) Write-Host ""; Write-Host $Message -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Fail    { param([string]$Message) Write-Host $Message -ForegroundColor Red }
function Write-Warn    { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }

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
    param(
        [string]$Label,
        [int]$ImagePullTimeoutSeconds = 600,
        [int]$ReadyTimeoutSeconds = 300
    )
    Write-Host "  Waiting for pod ($Label) to exist..." -NoNewline

    $elapsed = 0
    while ($elapsed -lt 60) {
        $podName = kubectl get pod -l $Label -n $Namespace -o jsonpath='{.items[0].metadata.name}' 2>$null
        if ($podName) { Write-Host " found: $podName" -ForegroundColor Green; break }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 5
        $elapsed += 5
    }
    if (-not $podName) { Write-Fail "Pod never appeared"; exit 1 }

    Write-Host "  Waiting for container to start..."
    $elapsed = 0
    while ($elapsed -lt $ImagePullTimeoutSeconds) {
        $phase = kubectl get pod -l $Label -n $Namespace -o jsonpath='{.items[0].status.phase}' 2>$null
        $reason = kubectl get pod -l $Label -n $Namespace -o jsonpath='{.items[0].status.containerStatuses[0].state.waiting.reason}' 2>$null
        
        if ($phase -eq "Running") { Write-Host "  running" -ForegroundColor Green; break }
        if ($reason -eq "ErrImagePull" -or $reason -eq "ImagePullBackOff") {
            Write-Fail "Image pull failed: $reason"
            kubectl describe pod -l $Label -n $Namespace
            exit 1
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 10
        $elapsed += 10
    }
    if ($elapsed -ge $ImagePullTimeoutSeconds) {
        Write-Fail "Timed out waiting for pod to start after ${ImagePullTimeoutSeconds}s"
        kubectl describe pod -l $Label -n $Namespace
        exit 1
    }

    Write-Host "  Waiting for readiness probe..." -NoNewline
    kubectl wait --for=condition=ready pod -l $Label -n $Namespace --timeout="${ReadyTimeoutSeconds}s"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Fail "Pod not ready within ${ReadyTimeoutSeconds}s"
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
if ($Gpu) {
    minikube start --cpus 4 --memory 8192 --gpus all --driver docker
} else {
    minikube start --cpus 4 --memory 8192
}

if ($LASTEXITCODE -ne 0) { Write-Fail "minikube start failed"; exit 1 }
Write-Success "  minikube started"

# Verify GPU is visible to K8s (only when requested)
if ($Gpu) {
    Start-Sleep -Seconds 5
    $gpuCount = kubectl get node minikube -o jsonpath='{.status.allocatable.nvidia\.com/gpu}' 2>$null
    if (-not $gpuCount -or [int]$gpuCount -eq 0) {
        Write-Fail "Minikube node does not expose GPUs to Kubernetes."
        Write-Host ""
        Write-Host "  On Windows with Docker Desktop + WSL2, install the NVIDIA Container Toolkit"
        Write-Host "  inside the WSL2 distro that Docker uses:"
        Write-Host "    https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        Write-Host ""
        Write-Host "  After installing, restart Docker Desktop and run:"
        Write-Host "    minikube delete"
        Write-Host "    .\k8s\scripts\windows\Start-Minikube.ps1 -Gpu"
        exit 1
    }
    Write-Success "  GPUs available to cluster: $gpuCount"
}

Write-Host "  Verifying Ollama image in minikube..."
minikube ssh -- docker images | findstr ollama

Write-Host "  Pre-pulling ollama image into minikube (speed up future pod starts)..."
minikube ssh -- docker pull ollama/ollama:latest
Write-Success "  Ollama image cached"

$minikubeMem = minikube config get memory 2>$null
Write-Host "  Minikube allocated memory: ${minikubeMem}MB"
if ([int]$minikubeMem -lt 6144) {
    Write-Warn "  WARNING: minikube has less than 6GB RAM. Backend may OOMKill."
    Write-Warn "  Run: minikube delete && minikube start --memory 8192"
}

# -----------------------------------------------------
# Step 2: Build images inside minikube Docker daemon
# -----------------------------------------------------
Write-Step "Step 2/6 - Building images inside minikube..."

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

docker build -f docker/Dockerfile.mlflow   -t edu-helpai-mlflow:latest   .
if ($LASTEXITCODE -ne 0) { Write-Fail "MLflow image build failed";   exit 1 }

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

$secretKey = python -c "import secrets; print(secrets.token_hex(32))"
if (-not $secretKey -or $secretKey.Length -lt 32) {
    Write-Fail "Failed to generate SECRET_KEY"
    exit 1
}

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
    Write-Host "  Removing previous CPU deployment (if any)..."
    kubectl delete deployment ollama -n $Namespace --ignore-not-found=$true | Out-Null
    Start-Sleep -Seconds 5

    Write-Host "  Deploying NVIDIA device plugin..."
    Invoke-Kubectl @("apply", "-f", "k8s/nvidia-device-plugin.yaml")
    Start-Sleep -Seconds 5

    Invoke-Kubectl @("apply", "-f", "k8s/ollama-gpu-deployment.yaml")
} else {
    Write-Host "  Removing previous GPU deployment (if any)..."
    kubectl delete deployment ollama-gpu -n $Namespace --ignore-not-found=$true | Out-Null
    Start-Sleep -Seconds 5

    Invoke-Kubectl @("apply", "-f", "k8s/ollama-deployment.yaml")
}

Wait-PodReady -Label "app=ollama" -ImagePullTimeoutSeconds 600 -ReadyTimeoutSeconds 300

$ollamaPod = kubectl get pod -n $Namespace -l app=ollama -o jsonpath='{.items[0].metadata.name}'

Write-Host "  Pulling mistral:7b (takes a few minutes)..."
kubectl exec -n $Namespace $ollamaPod -- ollama pull mistral:7b

Write-Host "  Pulling nomic-embed-text..."
kubectl exec -n $Namespace $ollamaPod -- ollama pull nomic-embed-text

Write-Success "  Ollama ready with models"

# -------------------------------------
# Step 5: Deploy backend + frontend + mlflow
# -------------------------------------
Write-Step "Step 5/6 - Deploying backend, frontend and MLflow..."
Invoke-Kubectl @("apply", "-f", "k8s/backend-deployment.yaml")
Invoke-Kubectl @("apply", "-f", "k8s/frontend-deployment.yaml")
Invoke-Kubectl @("apply", "-f", "k8s/mlflow-deployment.yaml")
Wait-PodReady -Label "app=backend"
Write-Success "  Backend, frontend and MLflow deployed"

# -----------------------------------------
# Step 6: Execute Port-Forwarding script
# -----------------------------------------
Write-Step "Step 6/6 - Starting port-forwards..."
Write-Host ""
Write-Host "  Starting Connect-Minikube to forward all services..." -ForegroundColor Cyan
Write-Host "  (Press Ctrl+C at any time to stop forwarding)" -ForegroundColor Yellow

& "$(Split-Path $PSCommandPath)\Connect-Minikube.ps1" -Namespace $Namespace