# file scripts/windows/Start-EduHelpAI.ps1

# Full startup automation for Edu-HelpAI on Windows (PowerShell)

# USAGE:
#   .\scripts\windows\Start-EduHelpAI.ps1    # CPU
#   .\scripts\windows\Start-EduHelpAI.ps1 -Gpu    # GPU

# Requirements:
#  - Docker Desktop for Windows
#  - PowerShell 7+

# -----------
# CONFIG
# -----------
param(
    [switch]$Gpu,
    [int]$MaxHealthWait = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$OllamaModels     = @("mistral:7b", "nomic-embed-text")
$ComposeFile      = "docker-compose.yaml"
$OllamaContainer  = "edu_ollama"
$OllamaService    = "ollama"
$BackendContainer = "edu_backend"
$BackendService   = "backend"

# -------------
# HELPERS FUNC
# -------------
function Write-Step    { param([string]$Message) Write-Host ""; Write-Host $Message -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Fail    { param([string]$Message) Write-Host $Message -ForegroundColor Red }


function Wait-Healthy {
    param(
        [string]$ContainerName,
        [string]$ServiceName,
        [int]$TimeoutSeconds = $MaxHealthWait
    )
    Write-Host "  Waiting for $ContainerName to become healthy..." -NoNewline
    $elapsed = 0
    while ($true) {
        try {
            $status = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>$null
        } catch {
            $status = "unknown"
        }
        if ($status -eq "healthy") { Write-Host " OK" -ForegroundColor Green; return }
        if ($elapsed -ge $TimeoutSeconds) {
            Write-Host ""
            Write-Fail "ERROR: $ContainerName did not become healthy within ${TimeoutSeconds}s"
            Write-Host "  Last status: $status"
            Write-Host "  Last 20 log lines:"
            docker compose -f $ComposeFile logs $ServiceName --tail 20
            exit 1
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 5
        $elapsed += 5
    }
}


function Invoke-Compose {
    param([string[]]$Arguments)
    if ($Gpu) {
        docker compose -f $ComposeFile --profile gpu @Arguments
    } else {
        docker compose -f $ComposeFile @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "docker compose failed (exit code $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

 
# --------------------
# Preflight checks 
# --------------------
Write-Step "Checking prerequisites..."
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker not found. Install: https://docs.docker.com/desktop/windows/"
    exit 1
}
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Fail "Docker Desktop is not running."; exit 1 }

if ($Gpu) {
    Write-Host "  GPU mode (NVIDIA)" -ForegroundColor Yellow
    docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu20.04 nvidia-smi 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Fail "NVIDIA GPU not accessible in Docker."; exit 1 }
    Write-Success "  NVIDIA GPU detected"
} else {
    Write-Host "  CPU mode (pass -Gpu for NVIDIA)" -ForegroundColor Gray
}
Write-Success "  Docker is running"
 
# ----------------------
# Step 1: Build images 
# ----------------------
Write-Step "Step 1/5 - Building images..."
Invoke-Compose @("build")
Write-Success "  Images built"
 

# ------------------------
# Step 2: Start Ollama
# ------------------------
Write-Step "Step 2/5 - Starting Ollama..."
if ($Gpu) {
    Invoke-Compose @("up", "ollama-gpu", "-d")
} else {
    Invoke-Compose @("up", "ollama", "-d")
}
Wait-Healthy -ContainerName $OllamaContainer -ServiceName $OllamaService

# -------------------------
# Step 3: Pull models
# -------------------------
Write-Step "Step 3/5 - Pulling models (skips if cached)..."
foreach ($model in $OllamaModels) {
    Write-Host "  -> $model"
    docker exec $OllamaContainer ollama pull $model
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to pull: $model"; exit 1 }
}
Write-Success "  All models ready"

# -----------------------------
# Step 4: Start all services
# -----------------------------
Write-Step "Step 4/5 - Starting backend, frontend, MLflow..."
Invoke-Compose @("up", "-d")
Wait-Healthy -ContainerName $BackendContainer -ServiceName $BackendService

# -------------------------
# Step 5: Print status
# -------------------------
Write-Step "Step 5/5 - Status"
Invoke-Compose @("ps")

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Success "  Edu-HelpAI is running!"
Write-Host "  Chat UI  -> http://localhost:8001" -ForegroundColor White
Write-Host "  API docs -> http://localhost:8000/docs" -ForegroundColor White
Write-Host "  MLflow   -> http://localhost:5000" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green