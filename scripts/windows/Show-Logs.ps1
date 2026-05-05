# scripts/windows/Show-Logs.ps1
#
# Tail logs for one or all services.
# Usage:
#   .\scripts\Show-Logs.ps1                    # all services
#   .\scripts\Show-Logs.ps1 -Service backend   # backend only
#   .\scripts\Show-Logs.ps1 -Service frontend
#   .\scripts\Show-Logs.ps1 -Service ollama

param(
    [string]$Service = ""
)

if ($Service) {
    docker compose logs $Service --follow
} else {
    docker compose logs --follow
}