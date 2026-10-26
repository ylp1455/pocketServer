#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/start-pocketserver"

mkdir -p "$BOOT_DIR"
printf '%s\n' \
  '#!/data/data/com.termux/files/usr/bin/bash' \
  'termux-wake-lock 2>/dev/null || true' \
  "nohup bash '$PROJECT_DIR/scripts/start-termux-auto.sh' > '$HOME/pocketserver-auto.log' 2>&1 &" \
  > "$BOOT_SCRIPT"
chmod 700 "$BOOT_SCRIPT"

echo "Boot launcher created at $BOOT_SCRIPT"
echo "Install and open the Termux:Boot app once to enable it after phone restarts."
