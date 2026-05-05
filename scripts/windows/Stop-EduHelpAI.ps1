# scripts/windows/Stop-EduHelpAI.ps1
#
# Stop all Edu-HelpAI Docker Compose services.
# Usage:
#   .\scripts\Stop-EduHelpAI.ps1              # stop, keep data
#   .\scripts\Stop-EduHelpAI.ps1 -Clean       # stop + delete volumes (destructive)
#   .\scripts\Stop-EduHelpAI.ps1 -Gpu         # stop GPU profile

param(
    [switch]$Clean,
    [switch]$Gpu
)

$ProfileFlag = if ($Gpu) { "--profile gpu" } else { "" }

if ($Clean) {
    Write-Host "Stopping and removing all volumes (data will be lost)..." -ForegroundColor Yellow
    $confirm = Read-Host "Are you sure? This deletes all DB and model data. (y/N)"
    if ($confirm -ne "y") { Write-Host "Aborted."; exit 0 }
    Invoke-Expression "docker compose $ProfileFlag down -v"
} else {
    Write-Host "Stopping containers (data preserved)..." -ForegroundColor Cyan
    Invoke-Expression "docker compose $ProfileFlag down"
}

Write-Host "Done." -ForegroundColor Green
