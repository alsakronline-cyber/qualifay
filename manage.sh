#!/bin/bash
# ============================================================
# AI WhatsApp CRM — Management Script
# Usage: ./manage.sh [command]
# ============================================================

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m"

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${CYAN}[→]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

print_usage() {
  echo -e "${BOLD}Usage:${NC} ./manage.sh [command]"
  echo ""
  echo "Commands:"
  echo "  start        Start all services"
  echo "  stop         Stop all services"
  echo "  restart      Restart all services"
  echo "  status       Show service status + resource usage"
  echo "  logs         Follow all logs"
  echo "  logs-ai      Follow AI worker logs only"
  echo "  logs-wa      Follow Evolution API (WhatsApp) logs"
  echo "  update       Pull latest images and rebuild"
  echo "  backup       Backup PostgreSQL database"
  echo "  restore      Restore PostgreSQL from backup"
  echo "  shell-db     Open psql shell"
  echo "  shell-redis  Open redis-cli"
  echo "  ai-stats     Show AI usage stats from DB"
  echo "  wa-status    Check all WhatsApp instance states"
  echo "  reset-ai     Restart AI worker (clears stuck tasks)"
  echo "  resources    Show current memory and CPU per container"
}

case "$1" in

  start)
    info "Starting AI WhatsApp CRM..."
    docker compose up -d
    log "All services started"
    ;;

  stop)
    info "Stopping all services..."
    docker compose down
    log "Stopped"
    ;;

  restart)
    info "Restarting all services..."
    docker compose restart
    log "Restarted"
    ;;

  status)
    echo -e "${BOLD}Service Status:${NC}"
    docker compose ps
    echo ""
    echo -e "${BOLD}Resource Usage:${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
    ;;

  logs)
    docker compose logs -f --tail=100
    ;;

  logs-ai)
    docker compose logs -f --tail=100 celery_worker celery_beat
    ;;

  logs-wa)
    docker compose logs -f --tail=100 evolution
    ;;

  logs-backend)
    docker compose logs -f --tail=100 backend
    ;;

  update)
    info "Pulling latest images..."
    docker compose pull
    info "Rebuilding custom services..."
    docker compose build --no-cache backend celery_worker celery_beat frontend
    info "Restarting..."
    docker compose up -d
    log "Update complete"
    ;;

  backup)
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="backups/wacrm_${TIMESTAMP}.sql.gz"
    mkdir -p backups
    info "Backing up database to $BACKUP_FILE..."
    docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_FILE"
    log "Backup saved: $BACKUP_FILE ($(du -h $BACKUP_FILE | cut -f1))"
    ;;

  restore)
    if [ -z "$2" ]; then
      warn "Usage: ./manage.sh restore backups/wacrm_YYYYMMDD_HHMMSS.sql.gz"
      exit 1
    fi
    info "Restoring from $2..."
    zcat "$2" | docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB"
    log "Restore complete"
    ;;

  shell-db)
    docker compose exec postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB"
    ;;

  shell-redis)
    docker compose exec redis redis-cli -a "$REDIS_PASSWORD"
    ;;

  ai-stats)
    echo -e "${BOLD}AI Statistics:${NC}"
    docker compose exec postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c "
      SELECT
        COUNT(*) FILTER (WHERE is_ai_generated = true) AS ai_messages,
        COUNT(*) AS total_messages,
        ROUND(COUNT(*) FILTER (WHERE is_ai_generated = true) * 100.0 / NULLIF(COUNT(*), 0), 1) AS ai_pct
      FROM messages;
    "
    docker compose exec postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c "
      SELECT COUNT(*) AS total_contacts,
             AVG(lead_score) AS avg_lead_score,
             COUNT(*) FILTER (WHERE lead_score >= 70) AS hot_leads
      FROM contacts;
    "
    ;;

  wa-status)
    echo -e "${BOLD}WhatsApp Instance Status:${NC}"
    source .env
    curl -s -H "apikey: $EVOLUTION_API_KEY" \
      "http://localhost:8080/instance/fetchInstances" | \
      python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, list):
  for inst in data:
    name = inst.get('instance', {}).get('instanceName', '?')
    state = inst.get('instance', {}).get('state', '?')
    print(f'  {name}: {state}')
else:
  print(data)
" 2>/dev/null || echo "  Could not reach Evolution API"
    ;;

  reset-ai)
    info "Restarting AI worker..."
    docker compose restart celery_worker celery_beat
    log "AI worker restarted"
    ;;

  resources)
    echo -e "${BOLD}Container Resource Usage:${NC}"
    docker stats --no-stream \
      crm_postgres crm_redis crm_evolution crm_backend crm_celery crm_beat crm_frontend crm_nginx \
      --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
    echo ""
    echo -e "${BOLD}Host System:${NC}"
    free -h
    echo ""
    df -h /
    ;;

  *)
    print_usage
    ;;
esac
