#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BRANCH="${POCKETSERVER_UPDATE_BRANCH:-main}"

if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Automatic updates require a Git checkout."
  echo "Clone PocketServer into Termux instead of running the copy in shared storage."
  exit 1
fi

if ! git -C "$PROJECT_DIR" diff --quiet || ! git -C "$PROJECT_DIR" diff --cached --quiet; then
  echo "Update skipped because the PocketServer source has local changes."
  exit 1
fi

echo "Checking GitHub for PocketServer updates..."
if ! git -C "$PROJECT_DIR" fetch --quiet --prune origin "$BRANCH"; then
  echo "Update check failed; the current server will keep running."
  exit 1
fi

CURRENT="$(git -C "$PROJECT_DIR" rev-parse HEAD)"
REMOTE="$(git -C "$PROJECT_DIR" rev-parse "origin/$BRANCH")"

if [ "$CURRENT" = "$REMOTE" ]; then
  echo "PocketServer is already current."
  echo "POCKETSERVER_UPDATE=current"
  exit 0
fi

if ! git -C "$PROJECT_DIR" merge-base --is-ancestor "$CURRENT" "$REMOTE"; then
  echo "Update refused because the remote branch is not a safe fast-forward."
  exit 1
fi

if ! git -C "$PROJECT_DIR" merge --ff-only --quiet "$REMOTE"; then
  echo "Update failed; the current checkout was preserved."
  exit 1
fi

echo "PocketServer updated to $(git -C "$PROJECT_DIR" rev-parse --short HEAD)."
echo "POCKETSERVER_UPDATE=applied"
