# Registra y ejecuta los deployments programados de Prefect (health cada 5 min, auditoría SAGA cada 10 min).
#   powershell -ExecutionPolicy Bypass -File scripts\start-prefect.ps1
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root "observability\prefect"
$env:PREFECT_API_URL = "http://localhost:4200/api"
$env:KUBECONFIG = Join-Path $env:USERPROFILE ".kube\aegisvolt.yaml"
$env:PYTHONIOENCODING = "utf-8"
$env:PATH = "$env:USERPROFILE\.local\bin;" + $env:PATH
Start-Process -FilePath "uv" -ArgumentList "run", "python", "serve.py" -WorkingDirectory $dir -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $dir "serve.log") -RedirectStandardError (Join-Path $dir "serve.err.log")
Write-Output "Prefect serve iniciado (UI: http://localhost:4200 ; logs: $dir\serve.log)"
