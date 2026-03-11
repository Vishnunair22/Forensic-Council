<#
.SYNOPSIS
    Forensic Council - PowerShell Manager

.DESCRIPTION
    Manages Docker containers for the Forensic Council application.
    All commands use docs/docker/docker-compose.yml and .env automatically.

.PARAMETER Target
    The target to run: up, dev, build, down, down-clean, logs, prod, infra, rebuild-backend, cache-status

.EXAMPLE
    .\manage.ps1 dev

.EXAMPLE
    .\manage.ps1 up
#>

param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet('up', 'dev', 'build', 'down', 'down-clean', 'logs', 'prod', 'infra', 'rebuild-backend', 'cache-status')]
    [string]$Target
)

$ErrorActionPreference = 'Stop'

$ComposeFile = "docs/docker/docker-compose.yml"
$EnvFile = ".env"

# Verify .env exists
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing $EnvFile file. Copy .env.example to .env and configure."
    exit 1
}

switch ($Target) {
    'up' {
        Write-Host "Starting all services..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile up -d --build
    }
    'dev' {
        Write-Host "Starting with hot-reload enabled..." -ForegroundColor Cyan
        docker compose -f $ComposeFile -f docs/docker/docker-compose.dev.yml --env-file $EnvFile up -d --build
    }
    'build' {
        Write-Host "Building images..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile build
    }
    'down' {
        Write-Host "Stopping services (keeping volumes)..." -ForegroundColor Yellow
        docker compose -f $ComposeFile --env-file $EnvFile down
    }
    'down-clean' {
        Write-Host "Stopping services and wiping volumes..." -ForegroundColor Red
        docker compose -f $ComposeFile --env-file $EnvFile down -v
    }
    'logs' {
        Write-Host "Following logs (Ctrl+C to exit)..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile logs -f
    }
    'prod' {
        Write-Host "Starting production mode..." -ForegroundColor Cyan
        docker compose -f $ComposeFile -f docs/docker/docker-compose.prod.yml --env-file $EnvFile up -d --build
    }
    'infra' {
        Write-Host "Starting infrastructure services only..." -ForegroundColor Cyan
        docker compose -f docs/docker/docker-compose.infra.yml --env-file $EnvFile up -d
    }
    'rebuild-backend' {
        Write-Host "Rebuilding backend only..." -ForegroundColor Yellow
        docker compose -f $ComposeFile --env-file $EnvFile build backend
        docker compose -f $ComposeFile --env-file $EnvFile up -d --no-deps backend
    }
    'cache-status' {
        Write-Host "ML Model Cache Volumes:" -ForegroundColor Cyan
        docker volume ls | Select-String -Pattern "forensic-council"
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Command failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
