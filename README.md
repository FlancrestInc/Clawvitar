# Pi Avatar

Animated Raspberry Pi avatar for watching a remote OpenClaw gateway.

The system has two services:

- `openclaw-avatar-status`: runs on the OpenClaw server and exposes `GET /status`.
- `pi-avatar-monitor`: runs on the Pi, polls the status feed, and writes local renderer state.

The renderer stays on the Pi and displays prepared full-screen PNG frames from `assets/`.

## OpenClaw Server Install

Copy this folder to the OpenClaw server and run:

```bash
sudo ./scripts/install-openclaw-status-agent.sh
```

Edit `/etc/pi-avatar/avatar.env` if needed:

```ini
STATUS_BIND_HOST=0.0.0.0
STATUS_BIND_PORT=18888
OPENCLAW_SERVICE=openclaw-gateway.service
OPENCLAW_PORT=18789
OPENCLAW_RUNTIME_LOG=/home/flan/.openclaw/logs/gateway-runtime.log
OPENCLAW_CONFIG_AUDIT_LOG=/home/flan/.openclaw/logs/config-audit.jsonl
```

Start or restart:

```bash
sudo systemctl restart openclaw-avatar-status
```

Check the feed:

```bash
curl http://localhost:18888/status
```

## Raspberry Pi Install

Copy this folder to the Pi and run:

```bash
sudo ./scripts/install-pi.sh
```

Edit `/etc/pi-avatar/avatar.env`:

```ini
STATUS_URL=http://openclaw-server.local:18888/status
STATE_FILE=/var/lib/pi-avatar/state.json
ASSET_DIR=/opt/pi-avatar/assets
HTTP_TIMEOUT_SECONDS=2
STALE_STATUS_SECONDS=15
```

Start or restart:

```bash
sudo systemctl restart pi-avatar-monitor pi-avatar-renderer
```

## Status Response

`GET /status` returns JSON:

```json
{
  "ok": true,
  "state": "working",
  "detail": "Recent OpenClaw tool/work activity",
  "updated": "2026-05-05T13:12:00-06:00",
  "service": {
    "active": true,
    "port_listening": true,
    "cpu_percent": 18.4
  }
}
```

Valid states are `booting`, `idle`, `thinking`, `working`, `success`, `error`, and `offline`.

## Asset Processing

Runtime loads prepared frames from `assets/<state>/00.png`. Spritesheets are processed before deployment.

Put source files under `source-assets/`:

- `background.png`
- one spritesheet per state
- `manifest.json`

See `source-assets/manifest.example.json` for grid and explicit-frame examples.

Generate deployable frames:

```bash
python3 process_assets.py --source source-assets --output assets --manifest manifest.json
```

## Development

Run tests:

```bash
python3 -m unittest test_monitor.py
```

Compile-check entrypoints:

```bash
python3 -m py_compile monitor.py renderer.py status_agent.py process_assets.py pi_avatar/*.py
```
