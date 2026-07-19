#!/bin/bash
# ============================================================
# Incremental redeploy after a code change. Run ON THE SERVER.
#
#   Usage:  ./scripts/redeploy.sh prod|dev [service ...]
#
#   ./scripts/redeploy.sh prod                  # rebuild+recreate all app services
#   ./scripts/redeploy.sh prod backend          # just the backend
#   ./scripts/redeploy.sh dev  frontend_dev      # just the dev frontend
#
# Safety net (the point of this script):
#   * --force-recreate  — a rebuilt image is always picked up (a plain `up -d` once
#                         left the Celery worker on stale code for hours).
#   * health gate       — after recreate, HTTP services must return 200 and every
#                         container must stay Up. If not, ALL touched services are
#                         rolled back to their previous image and the deploy fails.
# ============================================================
set -euo pipefail

ENV="${1:-prod}"
shift || true

case "$ENV" in
  prod)
    DIR="/home/ubuntu/qaulifay"; CF="docker-compose.yml"; BRANCH="production"
    DEFAULT_SERVICES=(backend frontend celery_worker celery_beat)
    BACKEND_HEALTH="http://127.0.0.1:5000/health"
    FRONTEND_HEALTH="http://127.0.0.1:3000/"
    ;;
  dev)
    DIR="/home/ubuntu/qaulifay-dev"; CF="docker-compose.dev.yml"; BRANCH="development"
    DEFAULT_SERVICES=(backend_dev frontend_dev celery_dev_worker)
    BACKEND_HEALTH="http://127.0.0.1:5001/health"
    FRONTEND_HEALTH="http://127.0.0.1:3001/"
    ;;
  *)
    echo "usage: $0 prod|dev [service ...]" >&2; exit 1 ;;
esac

if [ "$#" -gt 0 ]; then SERVICES=("$@"); else SERVICES=("${DEFAULT_SERVICES[@]}"); fi

cd "$DIR"
dc() { docker compose -f "$CF" "$@"; }

# Container name for a compose service (so we can inspect image id / running state).
cname() { dc ps -q "$1"; }

# HTTP health URL for a service, or empty (non-HTTP services just get a running check).
health_url() {
  case "$1" in
    backend|backend_dev)  echo "$BACKEND_HEALTH" ;;
    frontend|frontend_dev) echo "$FRONTEND_HEALTH" ;;
    *) echo "" ;;
  esac
}

echo "==> [$ENV] git pull origin $BRANCH"
git pull origin "$BRANCH"

# Remember each service's current image id (to roll back to) AND its image name/tag
# (the stable reference compose recreates from — only the id changes across builds).
declare -A OLD_ID OLD_NAME
for s in "${SERVICES[@]}"; do
  cid="$(cname "$s" || true)"
  if [ -n "$cid" ]; then
    OLD_ID[$s]="$(docker inspect --format '{{.Image}}' "$cid" 2>/dev/null || true)"
    OLD_NAME[$s]="$(docker inspect --format '{{.Config.Image}}' "$cid" 2>/dev/null || true)"
  fi
done

echo "==> [$ENV] build: ${SERVICES[*]}"
dc build "${SERVICES[@]}"

echo "==> [$ENV] recreate (force): ${SERVICES[*]}"
dc up -d --force-recreate "${SERVICES[@]}"

# ── Health gate ───────────────────────────────────────────────────────────────
check_service() {
  local s="$1" url; url="$(health_url "$s")"
  local cid; cid="$(cname "$s" || true)"
  [ -z "$cid" ] && { echo "   $s: no container"; return 1; }
  # Container must be running (not restart-looping).
  local state; state="$(docker inspect --format '{{.State.Running}}' "$cid" 2>/dev/null || echo false)"
  [ "$state" != "true" ] && { echo "   $s: not running"; return 1; }
  if [ -n "$url" ]; then
    for _ in $(seq 1 20); do
      code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || echo 000)"
      [ "$code" = "200" ] && { echo "   $s: healthy ($code)"; return 0; }
      sleep 1.5
    done
    echo "   $s: unhealthy (last $code)"; return 1
  fi
  # Non-HTTP (celery/beat): give it a moment, then confirm still up.
  sleep 4
  state="$(docker inspect --format '{{.State.Running}}' "$cid" 2>/dev/null || echo false)"
  [ "$state" = "true" ] && { echo "   $s: up"; return 0; }
  echo "   $s: crashed after start"; return 1
}

echo "==> [$ENV] health check"
FAILED=()
for s in "${SERVICES[@]}"; do
  check_service "$s" || FAILED+=("$s")
done

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "!!! [$ENV] health check FAILED for: ${FAILED[*]} — rolling back"
  rolled=0
  for s in "${SERVICES[@]}"; do
    if [ -n "${OLD_ID[$s]:-}" ] && [ -n "${OLD_NAME[$s]:-}" ]; then
      # Re-point the stable image name back to the previous image id, then recreate.
      docker tag "${OLD_ID[$s]}" "${OLD_NAME[$s]}" 2>/dev/null && rolled=1 || true
    else
      echo "   $s: no previous image recorded (first deploy?) — cannot auto-roll-back"
    fi
  done
  [ "$rolled" = "1" ] && dc up -d --force-recreate "${SERVICES[@]}"
  echo "!!! [$ENV] rolled back to previous images. Deploy aborted."
  dc ps
  exit 1
fi

echo "==> [$ENV] all healthy"
dc ps
echo "==> done"
