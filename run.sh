#!/bin/bash
# BTCRadar convenience launcher
set -e

cd "$(dirname "$0")"

# Resolve port for launcher messages/port cleanup.
# The app itself reads BTCRADAR_PORT when set, otherwise config.yaml.
if [ -n "${BTCRADAR_PORT:-}" ]; then
  PORT="${BTCRADAR_PORT}"
else
  PORT="$(awk '/^app:/{in_app=1; next} /^[^[:space:]]/{in_app=0} in_app && /^[[:space:]]+port:/{print $2; exit}' config.yaml)"
  PORT="${PORT:-5005}"
fi

# Free the port if something is already listening on it
if command -v fuser >/dev/null 2>&1; then
  if fuser -s "${PORT}/tcp" 2>/dev/null; then
    echo "Port ${PORT} is busy — killing previous process..."
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 1
  fi
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "Creating venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing requirements..."
pip install -q -r requirements.txt

echo "Starting BTCRadar Dashboard at http://localhost:${PORT}"

python -m src.app
