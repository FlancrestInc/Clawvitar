#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/pi-avatar"
CONFIG_DIR="/etc/pi-avatar"
CONFIG_FILE="${CONFIG_DIR}/avatar.env"

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}"

cp -a "${ROOT_DIR}/pi_avatar" "${INSTALL_DIR}/"
cp "${ROOT_DIR}/status_agent.py" "${ROOT_DIR}/requirements.txt" "${INSTALL_DIR}/"

python3 -m pip install -r "${INSTALL_DIR}/requirements.txt"

if [ ! -f "${CONFIG_FILE}" ]; then
  cat > "${CONFIG_FILE}" <<'EOF'
STATUS_BIND_HOST=0.0.0.0
STATUS_BIND_PORT=18888
OPENCLAW_SERVICE=openclaw-gateway.service
OPENCLAW_PORT=18789
OPENCLAW_RUNTIME_LOG=/home/flan/.openclaw/logs/gateway-runtime.log
OPENCLAW_CONFIG_AUDIT_LOG=/home/flan/.openclaw/logs/config-audit.jsonl
EOF
fi

cp "${ROOT_DIR}/systemd/openclaw-avatar-status.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable openclaw-avatar-status.service

echo "Installed OpenClaw avatar status agent. Edit ${CONFIG_FILE}, then run:"
echo "  sudo systemctl restart openclaw-avatar-status"
