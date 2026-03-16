<#
.SYNOPSIS
    Forensic Council - PowerShell Manager

.DESCRIPTION
    Manages Docker containers for the Forensic Council application.
    All commands use docs/docker/docker-compose.yml and .env automatically.

.PARAMETER Target
    The target to run: up, dev, build, down, down-clean, logs, prod, infra,
    rebuild-backend, cache-status, shell-backend, shell-frontend, migrate,
    init-db, health

.EXAMPLE
    .\manage.ps1 dev

.EXAMPLE
    .\manage.ps1 up
#>

param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet('up', 'dev', 'build', 'down', 'down-clean', 'logs', 'prod', 'infra',
                 'rebuild-backend', 'cache-status', 'shell-backend', 'shell-frontend',
                 'migrate', 'init-db', 'health')]
    [string]$Target
)

$ErrorActionPreference = 'Stop'

$ComposeFile   = "docs/docker/docker-compose.yml"
$DevOverride   = "docs/docker/docker-compose.dev.yml"
$ProdOverride  = "docs/docker/docker-compose.prod.yml"
$InfraOverride = "docs/docker/docker-compose.infra.yml"
$EnvFile       = ".env"

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
        docker compose -f $ComposeFile -f $DevOverride --env-file $EnvFile up -d --build
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
        Write-Host "Stopping services and wiping volumes... (DESTRUCTIVE)" -ForegroundColor Red
        $confirm = Read-Host "Are you sure? This cannot be undone [y/N]"
        if ($confirm -ne 'y') { Write-Host "Aborted."; exit 0 }
        docker compose -f $ComposeFile --env-file $EnvFile down -v
    }
    'logs' {
        Write-Host "Following logs (Ctrl+C to exit)..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile logs -f
    }
    'prod' {
        Write-Host "Starting production mode..." -ForegroundColor Cyan
        docker compose -f $ComposeFile -f $ProdOverride --env-file $EnvFile up -d --build
    }
    'infra' {
        # IMPORTANT: infra overlay only sets replicas=0 for app services.
        # It MUST be composed on top of the main file which defines postgres/redis/qdrant.
        Write-Host "Starting infrastructure services only (postgres, redis, qdrant)..." -ForegroundColor Cyan
        docker compose -f $ComposeFile -f $InfraOverride --env-file $EnvFile up -d
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
    'shell-backend' {
        Write-Host "Opening shell in backend container..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile exec backend bash
    }
    'shell-frontend' {
        Write-Host "Opening shell in frontend container..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile exec frontend sh
    }
    'migrate' {
        Write-Host "Running database migrations..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile exec backend python -m core.migrations
    }
    'init-db' {
        Write-Host "Running database initialisation..." -ForegroundColor Cyan
        docker compose -f $ComposeFile --env-file $EnvFile exec backend python scripts/init_db.py
    }
    'health' {
        Write-Host "Querying health endpoint..." -ForegroundColor Cyan
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
            $response | ConvertTo-Json -Depth 5
        } catch {
            Write-Error "Health check failed -- is the API running? $_"
            exit 1
        }
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Command failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
