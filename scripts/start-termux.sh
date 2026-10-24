#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_SHARED="$HOME/storage/shared/PocketServer"

if [ -d "$HOME/storage/shared" ]; then
  DATA_DIR="${POCKETSERVER_HOME:-$DEFAULT_SHARED}"
else
  DATA_DIR="${POCKETSERVER_HOME:-$HOME/PocketServerData}"
  echo "Shared storage is unavailable; using $DATA_DIR"
  echo "Run termux-setup-storage if you want files visible to Android apps."
fi

mkdir -p "$DATA_DIR"
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

cd "$PROJECT_DIR"
echo "Starting PocketServer with data at $DATA_DIR"
exec python -m pocketserver --host 0.0.0.0 --port "${POCKETSERVER_PORT:-8080}" --data-dir "$DATA_DIR" --no-open
