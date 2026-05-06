# filek8s/scripts/windows/Connect-Minikube.ps1
#
# Starts port-forwarding for all Edu-HelpAI services in the background.
# Press Ctrl+C to stop all forwards.
#
# Usage:
#   .\k8s\scripts\windows\Connect-Minikube.ps1

param(
    [string]$Namespace = "edu-helpai",
    [int]$FrontendPort = 8001,
    [int]$BackendPort  = 8000,
    [int]$OllamaPort   = 11434
)

Set-StrictMode -Version Latest

$forwards = @(
    @{ Service = "frontend-service"; Local = $FrontendPort; Remote = 8001;  Label = "Chat UI " },
    @{ Service = "backend-service";  Local = $BackendPort;  Remote = 8000;  Label = "API     " },
    @{ Service = "ollama-service";   Local = $OllamaPort;   Remote = 11434; Label = "Ollama  " }
)

$jobs = @()

Write-Host ""
Write-Host "Starting port-forwards..." -ForegroundColor Cyan

foreach ($fwd in $forwards) {
    $svc   = $fwd.Service
    $local = $fwd.Local
    $remote = $fwd.Remote
    $ns    = $Namespace

    $job = Start-Job -ScriptBlock {
        param($svc, $local, $remote, $ns)
        kubectl port-forward "svc/$svc" "${local}:${remote}" -n $ns 2>&1
    } -ArgumentList $svc, $local, $remote, $ns

    $jobs += @{ Job = $job; Forward = $fwd }
    Write-Host ("  [{0}]  http://localhost:{1}" -f $fwd.Label, $fwd.Local) -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Edu-HelpAI is accessible at:" -ForegroundColor Green
Write-Host ""
Write-Host ("  Chat UI   ->  http://localhost:{0}" -f $FrontendPort) -ForegroundColor White
Write-Host ("  API docs  ->  http://localhost:{0}/docs" -f $BackendPort) -ForegroundColor White
Write-Host ("  Ollama    ->  http://localhost:{0}" -f $OllamaPort) -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop all port-forwards." -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Green

# Register cleanup on Ctrl+C
$null = Register-EngineEvent PowerShell.Exiting -Action {
    foreach ($entry in $jobs) {
        Stop-Job  $entry.Job -ErrorAction SilentlyContinue
        Remove-Job $entry.Job -ErrorAction SilentlyContinue
    }
}

# Keep running, print job output and restart dead forwards
try {
    while ($true) {
        Start-Sleep -Seconds 5

        foreach ($entry in $jobs) {
            $job = $entry.Job
            $fwd = $entry.Forward

            # Print any new output from the job
            $output = Receive-Job $job -ErrorAction SilentlyContinue
            if ($output) {
                Write-Host ("  [{0}] {1}" -f $fwd.Label.Trim(), $output) -ForegroundColor DarkGray
            }

            # Restart if the job died unexpectedly
            if ($job.State -eq "Failed" -or $job.State -eq "Stopped") {
                Write-Host ("  [{0}] reconnecting..." -f $fwd.Label.Trim()) -ForegroundColor Yellow
                $svc    = $fwd.Service
                $local  = $fwd.Local
                $remote = $fwd.Remote
                $ns     = $Namespace

                $newJob = Start-Job -ScriptBlock {
                    param($svc, $local, $remote, $ns)
                    kubectl port-forward "svc/$svc" "${local}:${remote}" -n $ns 2>&1
                } -ArgumentList $svc, $local, $remote, $ns

                Stop-Job   $job -ErrorAction SilentlyContinue
                Remove-Job $job -ErrorAction SilentlyContinue
                $entry.Job = $newJob
            }
        }
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping port-forwards..." -ForegroundColor Yellow
    foreach ($entry in $jobs) {
        Stop-Job   $entry.Job -ErrorAction SilentlyContinue
        Remove-Job $entry.Job -ErrorAction SilentlyContinue
    }
    Write-Host "Done." -ForegroundColor Green
}