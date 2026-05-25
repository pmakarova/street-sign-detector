# start.ps1
$ErrorActionPreference = "Stop"

try {
    nvidia-smi | Out-Null
    Write-Host "GPU found - starting with GPU acceleration" -ForegroundColor Green
    $profile = "gpu"
} catch {
    Write-Host "No GPU - running on CPU" -ForegroundColor Cyan
    $profile = "cpu"
}

docker compose --profile $profile up --build -d

Write-Host ""
Write-Host "----------------------------------------"
Write-Host "  Frontend:    http://localhost"
Write-Host "  Swagger:     http://localhost:8000/docs"
Write-Host "  Prometheus:  http://localhost:9090"
Write-Host "  Grafana:     http://localhost:3000 (admin/admin)"
Write-Host "----------------------------------------"