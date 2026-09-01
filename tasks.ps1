# Tareas comunes para Windows PowerShell (mismos targets que el Makefile).
# Uso:            ./tasks.ps1 lint
# Todas:          ./tasks.ps1 ci
# ASCII-only (PowerShell 5.1 no lee UTF-8 sin BOM).
param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "test", "lint", "format", "format-check", "ci", "hooks", "docker-up")]
    [string]$Tarea = "ci"
)

$Fallas = 0
function Ejecutar([string[]]$Argumentos) {
    $Comando = @("-m") + $Argumentos
    Write-Host "== $($Argumentos -join ' ') ==" -ForegroundColor Cyan
    python @Comando 2>&1
    if ($LASTEXITCODE -ne 0) { $script:Fallas++ }
}

switch ($Tarea) {
    "install" { python -m pip install -e ".[dev]" }
    "test" { Ejecutar @("pytest", "-q") }
    "lint" { Ejecutar @("ruff", "check", "src", "tests") }
    "format" {
        Ejecutar @("ruff", "check", "src", "tests", "--fix")
        Ejecutar @("black", "src", "tests")
    }
    "format-check" { Ejecutar @("black", "--check", "src", "tests") }
    "ci" {
        Ejecutar @("ruff", "check", "src", "tests")
        Ejecutar @("black", "--check", "src", "tests")
        Ejecutar @("pytest", "-q")
    }
    "hooks" { python -m pre_commit install }
    "docker-up" {
        if (-not (Test-Path ".env")) {
            Write-Host "== Crea .env desde .env.example primero ==" -ForegroundColor Yellow
            exit 1
        }
        docker compose -f docker/docker-compose.yml up --build
    }
}

if ($Fallas -gt 0) {
    Write-Host "Tarea $Tarea termino con $Fallas fallas." -ForegroundColor Red
    exit 1
}