# Arranca el self-hosted runner de GitHub Actions (label aegisvolt-local) en segundo plano.
#   powershell -ExecutionPolicy Bypass -File scripts\start-runner.ps1
# Requisitos en PATH: Git Bash, docker, terraform, kubectl, aws, uv, helm, kubectl-argo-rollouts.
$runner = Join-Path $env:USERPROFILE "actions-runner"
$helm = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Helm.Helm*\windows-amd64" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
$extra = @("C:\Program Files\Git\bin", "C:\Program Files\GitHub CLI", "$env:USERPROFILE\bin",
           "$env:USERPROFILE\.local\bin", $helm) | Where-Object { $_ -and (Test-Path $_) }
$env:PATH = (($extra -join ";") + ";" + $env:PATH)
if (Get-Process -Name "Runner.Listener" -ErrorAction SilentlyContinue) {
  Write-Output "El runner ya está en ejecución."
  exit 0
}
Start-Process -FilePath (Join-Path $runner "run.cmd") -WorkingDirectory $runner -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $runner "runner.log") -RedirectStandardError (Join-Path $runner "runner.err.log")
Write-Output "Runner iniciado (logs en $runner\runner.log)"
