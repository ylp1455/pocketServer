#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_SHARED="$HOME/storage/shared/PocketServer"
UPDATE_SECONDS="${POCKETSERVER_UPDATE_SECONDS:-604800}"

case "$UPDATE_SECONDS" in
  *[!0-9]*|'') echo "POCKETSERVER_UPDATE_SECONDS must be a positive number."; exit 1 ;;
esac
if [ "$UPDATE_SECONDS" -lt 300 ]; then
  echo "POCKETSERVER_UPDATE_SECONDS must be at least 300 seconds."
  exit 1
fi

if [ -d "$HOME/storage/shared" ]; then
  DATA_DIR="${POCKETSERVER_HOME:-$DEFAULT_SHARED}"
else
  DATA_DIR="${POCKETSERVER_HOME:-$HOME/PocketServerData}"
  echo "Shared storage is unavailable; using $DATA_DIR"
fi

mkdir -p "$DATA_DIR"
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

check_update() {
  UPDATE_OUTPUT="$(bash "$PROJECT_DIR/scripts/update-termux.sh" 2>&1)"
  UPDATE_STATUS=$?
  printf '%s\n' "$UPDATE_OUTPUT"
  [ "$UPDATE_STATUS" -eq 0 ] || return "$UPDATE_STATUS"
  case "$UPDATE_OUTPUT" in
    *POCKETSERVER_UPDATE=applied*) return 10 ;;
    *) return 0 ;;
  esac
}

# Check once at startup. If this script was updated, reload the new version.
check_update
INITIAL_STATUS=$?
if [ "$INITIAL_STATUS" -eq 10 ]; then
  exec bash "$PROJECT_DIR/scripts/start-termux-auto.sh"
fi

cd "$PROJECT_DIR"
echo "Starting PocketServer with weekly GitHub updates."
echo "Data: $DATA_DIR"
echo "Update interval: $UPDATE_SECONDS seconds"
python -m pocketserver --host 0.0.0.0 --port "${POCKETSERVER_PORT:-8080}" --data-dir "$DATA_DIR" --no-open &
SERVER_PID=$!
TIMER_PID=""

cleanup() {
  [ -z "$TIMER_PID" ] || kill "$TIMER_PID" 2>/dev/null || true
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

while kill -0 "$SERVER_PID" 2>/dev/null; do
  sleep "$UPDATE_SECONDS" &
  TIMER_PID=$!
  wait "$TIMER_PID" 2>/dev/null || true
  TIMER_PID=""
  kill -0 "$SERVER_PID" 2>/dev/null || break

  check_update
  UPDATE_STATUS=$?
  if [ "$UPDATE_STATUS" -eq 10 ]; then
    echo "Restarting PocketServer with the installed update..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    trap - INT TERM EXIT
    exec bash "$PROJECT_DIR/scripts/start-termux-auto.sh"
  fi
done

wait "$SERVER_PID"
SERVER_STATUS=$?
trap - INT TERM EXIT
exit "$SERVER_STATUS"
