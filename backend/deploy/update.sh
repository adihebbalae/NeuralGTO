#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# backend/deploy/update.sh
#
# Pull latest code and restart the API service.
# Run on the Oracle VM whenever you push a new version to main.
#
# Usage:
#   ssh ubuntu@<oracle-ip> "bash /opt/neuralgto/backend/deploy/update.sh"
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="/opt/neuralgto"
SERVICE_NAME="neuralgto-api"

cd "${INSTALL_DIR}"

echo "[update] Pulling latest code..."
git pull origin main

echo "[update] Installing / updating Python dependencies..."
source .venv/bin/activate
pip install --quiet -r backend/requirements.oracle.txt
deactivate

echo "[update] Restarting ${SERVICE_NAME}..."
sudo systemctl restart "${SERVICE_NAME}"

echo "[update] Waiting for service to be healthy..."
sleep 3
if curl -sf http://localhost:8000/api/health > /dev/null; then
    echo "[update] ✓ Health check passed."
    sudo systemctl status "${SERVICE_NAME}" --no-pager -l
else
    echo "[update] ✗ Health check failed — check logs:"
    sudo journalctl -u "${SERVICE_NAME}" --no-pager -n 40
    exit 1
fi
