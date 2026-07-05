#!/bin/bash
# ============================================================
# AI WhatsApp CRM — Deployment Script
# Ubuntu 22.04 LTS ARM64 (aarch64)
# ============================================================
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${CYAN}[→]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║    AI WhatsApp CRM — Deployment Script       ║"
echo "║    Ubuntu 22.04 ARM64 · Evolution API        ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Check requirements ────────────────────────────────────
command -v docker >/dev/null || err "Docker not installed. Run: curl -fsSL https://get.docker.com | sh"
command -v docker-compose >/dev/null 2>&1 || command -v docker compose >/dev/null || err "Docker Compose not found"
log "Docker available"

# ─── Check .env ────────────────────────────────────────────
if [ ! -f .env ]; then
  warn ".env not found — copying from .env.example"
  cp .env.example .env
  echo ""
  warn "IMPORTANT: Edit .env before continuing!"
  warn "Required: POSTGRES_PASSWORD, REDIS_PASSWORD, EVOLUTION_API_KEY,"
  warn "          OPENROUTER_API_KEY, SECRET_KEY, EVOLUTION_SERVER_URL"
  echo ""
  read -p "Press ENTER after editing .env to continue... "
fi
log ".env loaded"

# Load env
export $(grep -v '^#' .env | xargs)

# ─── Check required vars ───────────────────────────────────
required_vars="POSTGRES_PASSWORD REDIS_PASSWORD EVOLUTION_API_KEY OPENROUTER_API_KEY SECRET_KEY"
for var in $required_vars; do
  val="${!var}"
  if [ -z "$val" ] || echo "$val" | grep -q "CHANGE_ME"; then
    err "$var is not set or still has default value. Edit .env first."
  fi
done
log "Environment variables validated"

# ─── Install Docker Buildx (ARM64) ────────────────────────
info "Setting up Docker Buildx for ARM64..."
docker buildx create --use --name arm64-builder 2>/dev/null || true

# ─── Pull base images ──────────────────────────────────────
info "Pulling base images (ARM64 compatible)..."
docker pull postgres:15-alpine --platform linux/arm64 2>/dev/null || docker pull postgres:15-alpine
docker pull redis:7-alpine --platform linux/arm64 2>/dev/null || docker pull redis:7-alpine
docker pull evoapicloud/evolution-api:latest 2>/dev/null || warn "Evolution API pull failed — will retry on compose up"
docker pull nginx:alpine
log "Base images ready"

# ─── Build services ────────────────────────────────────────
info "Building backend..."
docker compose build backend celery_worker celery_beat

info "Building frontend..."
docker compose build frontend

log "All services built"

# ─── Start infrastructure first ────────────────────────────
info "Starting PostgreSQL and Redis..."
docker compose up -d postgres redis
sleep 5

# Wait for postgres
info "Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
  if docker compose exec postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
    log "PostgreSQL ready"
    break
  fi
  sleep 2
  echo -n "."
done

# ─── Start all services ────────────────────────────────────
info "Starting all services..."
docker compose up -d

sleep 8

# ─── Create default admin ──────────────────────────────────
info "Creating default admin user..."
docker compose exec backend python -c "
import asyncio
from app.core.database import AsyncSessionLocal, init_db
from app.models.models import User
from passlib.context import CryptContext
from app.core.config import settings

async def create_admin():
    await init_db()
    pwd = CryptContext(schemes=['bcrypt'], deprecated='auto')
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.email == settings.DEFAULT_ADMIN_EMAIL))
        if not result.scalar_one_or_none():
            admin = User(
                email=settings.DEFAULT_ADMIN_EMAIL,
                full_name='CRM Admin',
                hashed_password=pwd.hash(settings.DEFAULT_ADMIN_PASSWORD),
                is_admin=True,
            )
            db.add(admin)
            await db.commit()
            print(f'Admin created: {settings.DEFAULT_ADMIN_EMAIL}')
        else:
            print('Admin already exists')

asyncio.run(create_admin())
" 2>/dev/null && log "Admin user ready" || warn "Admin creation skipped (may already exist)"

# ─── Status check ──────────────────────────────────────────
echo ""
echo -e "${BOLD}Service Status:${NC}"
docker compose ps

# ─── Health check ──────────────────────────────────────────
echo ""
info "Running health checks..."
sleep 5

SERVER_IP=$(hostname -I | awk '{print $1}')

check_service() {
  local name=$1
  local url=$2
  if curl -sf "$url" >/dev/null 2>&1; then
    log "$name ✓"
  else
    warn "$name not responding yet (may still be starting)"
  fi
}

check_service "Backend API"    "http://localhost:5000/health"
check_service "Evolution API"  "http://localhost:8080/manager"
check_service "Frontend"       "http://localhost:80"

# ─── Done ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  AI WhatsApp CRM Deployed Successfully!       ${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}CRM Dashboard:${NC}    http://$SERVER_IP"
echo -e "  ${BOLD}API Docs:${NC}         http://$SERVER_IP/api/docs"
echo -e "  ${BOLD}Evolution Manager:${NC}http://$SERVER_IP:8080/manager"
echo -e "  ${BOLD}Admin Login:${NC}      $DEFAULT_ADMIN_EMAIL"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Open Evolution Manager → Create WhatsApp instance → Scan QR"
echo "  2. Login to CRM with your admin credentials"
echo "  3. Add your OpenRouter API key at openrouter.ai if not done"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  docker compose logs -f backend      # Backend logs"
echo "  docker compose logs -f celery_worker # AI worker logs"
echo "  docker compose restart backend       # Restart backend"
echo "  docker compose down                  # Stop all"
echo "  ./deploy.sh                          # Redeploy"
echo ""
