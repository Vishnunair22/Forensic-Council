param(
    [Parameter(Position=0)]
    [string]$Command,
    [Parameter(Position=1)]
    [string]$Service
)

$ErrorActionPreference = "Stop"

$COMPOSE = "docker compose -f docs/docker/docker-compose.yml --env-file .env"
$COMPOSE_DEV = "$COMPOSE -f docs/docker/docker-compose.dev.yml"
$COMPOSE_PROD = "$COMPOSE -f docs/docker/docker-compose.prod.yml"
$PROJECT_NAME = "forensic-council"

function Check-Env() {
    if (-not (Test-Path ".env")) {
        Write-Host "`n[X] ERROR: .env file not found." -ForegroundColor Red
        Write-Host "    Run: cp .env.example .env"
        Write-Host "    Then edit .env with your values.`n"
        exit 1
    }
    
    $envContent = Get-Content -Path ".env" -Raw
    if ($envContent -notmatch "NEXT_PUBLIC_DEMO_PASSWORD=[^\s]+") {
        Write-Host "`n[!] WARNING: NEXT_PUBLIC_DEMO_PASSWORD is not set in .env" -ForegroundColor Yellow
        Write-Host "    Edit .env and set a value for NEXT_PUBLIC_DEMO_PASSWORD.`n"
    }
}

function Invoke-Compose($CmdArgs) {
    # Using Invoke-Expression to correctly pass the full command string
    Invoke-Expression "$CmdArgs"
}

switch ($Command) {
    "up" {
        Check-Env
        Invoke-Compose "$COMPOSE up --build -d"
        Write-Host "`n[+] Services started. Frontend -> http://localhost:3000" -ForegroundColor Green
        Write-Host "[+] Backend API   -> http://localhost:8000`n" -ForegroundColor Green
    }
    "dev" {
        Check-Env
        Invoke-Compose "$COMPOSE_DEV up --build -d"
        Write-Host "`n[+] Development Services started." -ForegroundColor Cyan
    }
    "infra" {
        Invoke-Compose "docker compose -f docs/docker/docker-compose.infra.yml --env-file .env up -d"
        Write-Host "[+] Infrastructure started (Redis, Postgres, Qdrant)" -ForegroundColor Green
    }
    "build" {
        Check-Env
        Invoke-Compose "$COMPOSE build"
    }
    "rebuild" {
        Check-Env
        Write-Host "[*] Checking what changed requires git. To rebuild all safely, use rebuild-all." -ForegroundColor Cyan
        Write-Host "[*] To rebuild a specific service, use '.\manage.ps1 rebuild-backend' or '.\manage.ps1 rebuild-frontend'" -ForegroundColor Cyan
    }
    "rebuild-backend" {
        Check-Env
        Write-Host "[*] Building backend image (dep layers are cached)..."
        Invoke-Compose "$COMPOSE build backend"
        Write-Host "[*] Restarting backend service..."
        Invoke-Compose "$COMPOSE up -d --no-deps backend"
        Write-Host "[+] Backend rebuilt and restarted." -ForegroundColor Green
    }
    "rebuild-frontend" {
        Check-Env
        Write-Host "[*] Building frontend image (npm cache reused)..."
        Invoke-Compose "$COMPOSE build frontend"
        Write-Host "[*] Restarting frontend service..."
        Invoke-Compose "$COMPOSE up -d --no-deps frontend"
        Write-Host "[+] Frontend rebuilt and restarted." -ForegroundColor Green
    }
    "cache-status" {
        Write-Host "`n=== ML Model Volume Status ($PROJECT_NAME) ===" -ForegroundColor Cyan
        $volumes = @("hf_cache", "torch_cache", "easyocr_cache", "yolo_cache", "deepface_cache", "numba_cache", "calibration_models")
        foreach ($vol in $volumes) {
            $fullName = "${PROJECT_NAME}_${vol}"
            $exists = docker volume ls -q -f name="^${fullName}$"
            if ($exists) {
                # Try to get size
                try {
                    $size = docker run --rm -v "${fullName}:/data" alpine sh -c "du -sh /data 2>/dev/null | cut -f1"
                    Write-Host "  [+] $vol  ($size)" -ForegroundColor Green
                } catch {
                     Write-Host "  [+] $vol  (exists)" -ForegroundColor Green
                }
            } else {
                Write-Host "  [!] $vol  -> NOT CREATED YET (will populate on first run)" -ForegroundColor Yellow
            }
        }
    }
    "cache-warm" {
        Check-Env
        Write-Host "[*] Running model cache check inside backend container..." -ForegroundColor Cyan
        Invoke-Compose "$COMPOSE run --rm --no-deps -e SKIP_CACHE_CHECK=0 backend python scripts/model_cache_check.py"
    }
    "down" {
        Invoke-Compose "$COMPOSE down"
        Write-Host "[+] Services stopped. Model caches preserved." -ForegroundColor Green
    }
    "down-clean" {
        Write-Host "`n[!] WARNING: This will DELETE all Docker volumes including:" -ForegroundColor Yellow
        Write-Host "    - All ML model caches (hf_cache, torch_cache, easyocr_cache, etc.)"
        Write-Host "    - PostgreSQL database data"
        Write-Host "    - Redis data"
        Write-Host "`n    Models will be re-downloaded on next start (15-60 min).`n"
        $confirm = Read-Host "    Type 'yes' to confirm"
        if ($confirm -eq "yes") {
            Invoke-Compose "$COMPOSE down -v"
            Write-Host "[+] All services and volumes removed." -ForegroundColor Green
        } else {
            Write-Host "Aborted."
            exit 1
        }
    }
    "logs" {
        if ($Service) {
            Invoke-Compose "$COMPOSE logs -f $Service"
        } else {
            Invoke-Compose "$COMPOSE logs -f"
        }
    }
    "ps" {
        Invoke-Compose "$COMPOSE ps"
    }
    "prod" {
        Check-Env
        Invoke-Compose "$COMPOSE_PROD up --build -d"
    }
    "prune" {
        Invoke-Compose "docker image prune -f"
        Write-Host "[+] Dangling images removed." -ForegroundColor Green
    }
    "prune-all" {
        Invoke-Compose "docker system prune -f"
        Write-Host "[+] System pruned (volumes preserved)." -ForegroundColor Green
    }
    default {
        Write-Host "`nUsage: .\manage.ps1 <command>`n"
        Write-Host "Commands:"
        Write-Host "  up               Build and start all services"
        Write-Host "  dev              Start with hot-reload"
        Write-Host "  infra            Start only infrastructure (Postgres, Redis, Qdrant)"
        Write-Host "  build            Build images without starting"
        Write-Host "  rebuild-backend  Rebuild only backend"
        Write-Host "  rebuild-frontend Rebuild only frontend"
        Write-Host "  down             Stop services, KEEP volumes (models preserved)"
        Write-Host "  down-clean       Stop services, DELETE volumes (models wiped)"
        Write-Host "  logs [service]   Tail logs (optionally for a specific service)"
        Write-Host "  ps               Show container status"
        Write-Host "  cache-status     Show ML model cache volume status"
        Write-Host "  cache-warm       Pre-warm cache by running check script"
        Write-Host "  prod             Start production deploy with Caddy"
        Write-Host "  prune            Remove dangling Docker images`n"
    }
}
