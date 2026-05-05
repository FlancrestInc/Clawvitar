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
VENV_DIR="${INSTALL_DIR}/.venv"

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}"

cp -a "${ROOT_DIR}/pi_avatar" "${INSTALL_DIR}/"
cp "${ROOT_DIR}/status_agent.py" "${INSTALL_DIR}/"

if ! python3 -m venv "${VENV_DIR}"; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "python3 venv support is unavailable; installing python3-venv with apt."
    apt-get update
    apt-get install -y python3-venv
    rm -rf "${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
  else
    echo "Could not create ${VENV_DIR}. Install Python venv support, then rerun this installer." >&2
    exit 1
  fi
fi

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
