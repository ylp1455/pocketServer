#!/data/data/com.termux/files/usr/bin/bash
set -eu

if ! command -v pkg >/dev/null 2>&1; then
  echo "This setup script must be run inside Termux."
  exit 1
fi

echo "Updating Termux packages..."
pkg update -y
pkg upgrade -y

echo "Installing PocketServer requirements..."
pkg install -y python aria2 git

echo "Requesting access to shared phone storage..."
termux-setup-storage || true

echo
echo "Setup complete. Android may show a storage permission prompt."
echo "Start PocketServer with: bash scripts/start-termux.sh"
