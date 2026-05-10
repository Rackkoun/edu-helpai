# k8s/scripts/windows/Stop-Minikube.ps1
#
# Safely tear down Edu-HelpAI from minikube.
#
# Usage:
#   .\k8s\scripts\windows\Stop-Minikube.ps1              # delete namespace only (keep cluster)
#   .\k8s\scripts\windows\Stop-Minikube.ps1 -StopCluster # also stop minikube
#   .\k8s\scripts\windows\Stop-Minikube.ps1 -DeleteCluster # stop + delete minikube entirely

param(
    [switch]$StopCluster,
    [switch]$DeleteCluster
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Namespace = "edu-helpai"

function Write-Step    { param([string]$M) Write-Host ""; Write-Host $M -ForegroundColor Cyan }
function Write-Success { param([string]$M) Write-Host $M -ForegroundColor Green }
function Write-Warn    { param([string]$M) Write-Host $M -ForegroundColor Yellow }


# 1. Show what's running
Write-Step "Current state in namespace '$Namespace':"
kubectl get all -n $Namespace 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "  Namespace '$Namespace' not found — nothing to clean up."
}


# 2. Scale down deployments gracefully
Write-Step "Scaling down deployments..."
$deployments = kubectl get deployments -n $Namespace -o jsonpath='{.items[*].metadata.name}' 2>$null
if ($deployments) {
    foreach ($deploy in ($deployments -split ' ')) {
        Write-Host "  Scaling $deploy to 0..."
        kubectl scale deployment $deploy --replicas=0 -n $Namespace 2>$null | Out-Null
    }
    # Give pods 15s to terminate gracefully
    Start-Sleep -Seconds 15
}


# 3. Delete namespace (removes all resources inside it)
Write-Step "Deleting namespace '$Namespace' and all its resources..."
kubectl delete namespace $Namespace --timeout=60s 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Success "  Namespace deleted (pods, services, PVCs, configmaps, secrets all removed)"
} else {
    Write-Warn "  Namespace deletion timed out or already gone — continuing"
}

# 4. Optionally stop/delete minikube
if ($DeleteCluster) {
    Write-Step "Deleting minikube cluster entirely..."
    $confirm = Read-Host "  This deletes the cluster AND all cached images. Continue? (y/N)"
    if ($confirm -eq "y") {
        minikube delete
        Write-Success "  Minikube cluster deleted"
    } else {
        Write-Warn "  Skipped cluster deletion"
    }
} elseif ($StopCluster) {
    Write-Step "Stopping minikube (cluster preserved, can restart with minikube start)..."
    minikube stop
    Write-Success "  Minikube stopped"
} else {
    Write-Host ""
    Write-Warn "  Minikube cluster still running. Use:"
    Write-Host "  -StopCluster    to stop minikube (preserves data)" -ForegroundColor Gray
    Write-Host "  -DeleteCluster  to delete minikube entirely" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Success "  Cleanup complete"
Write-Host "============================================" -ForegroundColor Green