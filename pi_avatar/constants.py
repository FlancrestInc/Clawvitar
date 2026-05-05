from pathlib import Path

DEFAULT_STATE_FILE = Path("/var/lib/pi-avatar/state.json")
DEFAULT_ASSET_DIR = Path("/opt/pi-avatar/assets")
DEFAULT_ENV_FILE = Path("/etc/pi-avatar/avatar.env")

DEFAULT_STATUS_URL = "http://openclaw-server.local:18888/status"
DEFAULT_STATUS_BIND_HOST = "0.0.0.0"
DEFAULT_STATUS_BIND_PORT = 18888

OPENCLAW_SERVICE = "openclaw-gateway.service"
OPENCLAW_PORT = "18789"
RUNTIME_LOG = Path("/home/flan/.openclaw/logs/gateway-runtime.log")
CONFIG_AUDIT_LOG = Path("/home/flan/.openclaw/logs/config-audit.jsonl")

FAST_POLL_SECONDS = 0.2
HEALTH_POLL_SECONDS = 3.0
CPU_POLL_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 2.0
STALE_STATUS_SECONDS = 15.0

WORKING_CPU_THRESHOLD = 12.0
THINKING_CPU_THRESHOLD = 4.0

ERROR_HOLD_SECONDS = 10
SUCCESS_HOLD_SECONDS = 6
THINKING_HOLD_SECONDS = 4
LOG_LOOKBACK_LINES = 120
CONFIG_ERROR_WINDOW_SECONDS = 60

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480
FPS = 8
STATE_CHECK_SECONDS = 0.1
DEFAULT_STATE = "idle"

VALID_STATES = [
    "booting",
    "idle",
    "thinking",
    "working",
    "success",
    "error",
    "offline",
]

STATE_FPS = {
    "booting": 10,
    "idle": 4,
    "thinking": 8,
    "working": 14,
    "success": 8,
    "error": 10,
    "offline": 4,
}
