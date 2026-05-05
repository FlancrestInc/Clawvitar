#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/pi-avatar"
CONFIG_DIR="/etc/pi-avatar"
STATE_DIR="/var/lib/pi-avatar"
CONFIG_FILE="${CONFIG_DIR}/avatar.env"

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}"

cp -a "${ROOT_DIR}/pi_avatar" "${INSTALL_DIR}/"
cp -a "${ROOT_DIR}/assets" "${INSTALL_DIR}/"
cp "${ROOT_DIR}/monitor.py" "${ROOT_DIR}/renderer.py" "${ROOT_DIR}/process_assets.py" "${ROOT_DIR}/requirements.txt" "${INSTALL_DIR}/"

python3 -m pip install -r "${INSTALL_DIR}/requirements.txt"

if [ ! -f "${CONFIG_FILE}" ]; then
  cat > "${CONFIG_FILE}" <<'EOF'
STATUS_URL=http://openclaw-server.local:18888/status
STATE_FILE=/var/lib/pi-avatar/state.json
ASSET_DIR=/opt/pi-avatar/assets
HTTP_TIMEOUT_SECONDS=2
STALE_STATUS_SECONDS=15
EOF
fi

cp "${ROOT_DIR}/systemd/pi-avatar-monitor.service" /etc/systemd/system/
cp "${ROOT_DIR}/systemd/pi-avatar-renderer.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable pi-avatar-monitor.service pi-avatar-renderer.service

echo "Installed Pi Avatar. Edit ${CONFIG_FILE}, then run:"
echo "  sudo systemctl restart pi-avatar-monitor pi-avatar-renderer"
