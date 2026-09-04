#!/usr/bin/env bash
# GnKAlgo Oracle VM — update, start, stop, status (docker compose prod).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

usage() {
  cat <<'EOF'
Usage: ./scripts/update-oracle-vm.sh <command>

Commands:
  update   Pull latest git branch, rebuild images, start stack (default deploy)
  start    Start all services (no rebuild)
  stop     Stop and remove containers (keeps volumes / data)
  restart  Stop then start (no rebuild)
  status   Show container status + local health check

Environment overrides:
  REPO_DIR=/opt/gnkalgo
  BRANCH=main
  COMPOSE_FILE=docker-compose.prod.yml

Examples:
  cd /opt/gnkalgo
  ./scripts/update-oracle-vm.sh update
  ./scripts/update-oracle-vm.sh start
  ./scripts/update-oracle-vm.sh stop
EOF
}

compose() {
  docker compose -f "$REPO_DIR/$COMPOSE_FILE" "$@"
}

require_env() {
  if [[ ! -f "$REPO_DIR/.env" ]]; then
    echo "Missing $REPO_DIR/.env — copy from .env.production.example and configure secrets." >&2
    exit 1
  fi
}

cmd_status() {
  compose ps
  echo ""
  echo "==> Health (backend)"
  curl -fsS http://127.0.0.1:8000/health && echo "" || echo "backend not responding on :8000"
  echo "==> Public check: https://www.gnkalgo.com/health"
}

cmd_stop() {
  echo "==> Stopping GnKAlgo stack ($COMPOSE_FILE)"
  compose down
  echo "==> Stopped (postgres/redis data volumes preserved)"
}

cmd_start() {
  require_env
  echo "==> Starting GnKAlgo stack ($COMPOSE_FILE)"
  compose up -d
  cmd_status
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_update() {
  require_env
  cd "$REPO_DIR"

  echo "==> Repo: $REPO_DIR"
  echo "==> Branch: $BRANCH"

  if [[ ! -d .git ]]; then
    echo "Not a git repository: $REPO_DIR" >&2
    exit 1
  fi

  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull origin "$BRANCH"

  echo "==> Build and start ($COMPOSE_FILE)"
  compose up -d --build

  cmd_status
  echo ""
  echo "Update complete."
}

main() {
  local command="${1:-}"
  case "$command" in
    update) cmd_update ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
    -h|--help|help) usage ;;
    "")
      echo "No command given." >&2
      usage >&2
      exit 1
    ;;
    *)
      echo "Unknown command: $command" >&2
      usage >&2
      exit 1
    ;;
  esac
}

main "$@"
