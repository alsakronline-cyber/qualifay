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
# Always uses --force-recreate: `docker compose up -d` will NOT replace a running
# container when only the image changed underneath it, which once left the Celery
# worker running stale code after a rebuild. Forcing recreation avoids that class of bug.
# ============================================================
set -euo pipefail

ENV="${1:-prod}"
shift || true

case "$ENV" in
  prod)
    DIR="/home/ubuntu/qaulifay"
    CF="docker-compose.yml"
    BRANCH="production"
    DEFAULT_SERVICES=(backend frontend celery_worker celery_beat)
    ;;
  dev)
    DIR="/home/ubuntu/qaulifay-dev"
    CF="docker-compose.dev.yml"
    BRANCH="development"
    DEFAULT_SERVICES=(backend_dev frontend_dev celery_dev_worker)
    ;;
  *)
    echo "usage: $0 prod|dev [service ...]" >&2
    exit 1
    ;;
esac

# Rebuild only the services passed as extra args, or the full app set by default.
if [ "$#" -gt 0 ]; then
  SERVICES=("$@")
else
  SERVICES=("${DEFAULT_SERVICES[@]}")
fi

cd "$DIR"

echo "==> [$ENV] git pull origin $BRANCH"
git pull origin "$BRANCH"

echo "==> [$ENV] build: ${SERVICES[*]}"
docker compose -f "$CF" build "${SERVICES[@]}"

echo "==> [$ENV] recreate (force): ${SERVICES[*]}"
docker compose -f "$CF" up -d --force-recreate "${SERVICES[@]}"

echo "==> [$ENV] status"
docker compose -f "$CF" ps
echo "==> done"
