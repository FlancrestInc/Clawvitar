# Remote OpenClaw Avatar Design

Date: 2026-05-05

## Goal

Keep the animated avatar running on the Raspberry Pi while OpenClaw runs on a different server. The avatar should watch OpenClaw remotely, install cleanly on a new Pi with minimal configuration, and use a repeatable sprite pipeline for new spritesheet-based graphics.

## Architecture

Split the system into two small services:

- `pi-avatar-monitor`: runs on the Raspberry Pi, polls an HTTP status feed, maps the response to avatar state, and writes the local state JSON consumed by the renderer.
- `openclaw-avatar-status`: runs on the OpenClaw server, performs local OpenClaw health/activity checks, and exposes `GET /status`.

The renderer remains local to the Pi. It reads the state file and full-screen prepared PNG frames. It does not know how OpenClaw is monitored and does not slice spritesheets at runtime.

## Status Feed

The OpenClaw server companion exposes:

```http
GET /status
```

Example response:

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

The status agent should preserve the existing classification behavior from `monitor.py`:

- service stopped -> `offline`
- service active but gateway port unavailable -> `error`
- recent config audit warning -> `error`
- recent error-like log entry -> `error`
- recent completion-like log entry -> `success`
- recent tool/work log entry or high CPU -> `working`
- recent agent/model/request log entry or light CPU -> `thinking`
- otherwise -> `idle`

Short-lived hold behavior belongs in the OpenClaw server companion so the HTTP feed is already avatar-ready. The Pi monitor stays simple and portable.

## Pi Poller Behavior

The Pi monitor polls the configured status URL. The status response is the source of truth when it is fresh and valid.

The Pi writes `offline` when:

- the HTTP request times out
- the endpoint is unavailable
- the response is invalid JSON
- the response has an unknown state
- the response timestamp is stale

Otherwise it writes the reported `state`, `detail`, and local update timestamp to the renderer state file.

## Packaging

Use a conventional package layout:

```text
pi_avatar/
  renderer.py
  monitor.py
  status_agent.py
  config.py
  state.py
assets/
source-assets/
systemd/
  pi-avatar-renderer.service
  pi-avatar-monitor.service
  openclaw-avatar-status.service
scripts/
  install-pi.sh
  install-openclaw-status-agent.sh
requirements.txt
README.md
```

Default installed paths:

- application files: `/opt/pi-avatar`
- config: `/etc/pi-avatar/avatar.env`
- runtime state: `/var/lib/pi-avatar/state.json`
- deployable frames: `/opt/pi-avatar/assets`

The Pi installer should install the renderer, HTTP poller, assets, dependencies, config template, and systemd units. Minimal Pi configuration is the status URL:

```ini
STATUS_URL=http://openclaw-server.local:18888/status
```

The OpenClaw server installer should install only the status agent, its config, dependencies, and `openclaw-avatar-status.service`.

## Asset Pipeline

Runtime should only load prepared full-screen PNG frames. Spritesheet processing happens before deployment.

Source assets:

- `source-assets/background.png`: shared background
- `source-assets/<state>.png` or `source-assets/<state>/sheet.png`: spritesheet per avatar state
- `source-assets/manifest.json`: frame extraction and placement settings

The processor composites each sprite frame over the background and exports normalized frames:

```text
assets/<state>/00.png
assets/<state>/01.png
...
```

All exported frames are full-screen PNGs, defaulting to `800x480`.

The manifest supports two modes:

- `grid`: same-size frames arranged in a regular grid
- `frames`: explicit coordinates for different-sized sprites

Example manifest shape:

```json
{
  "canvas": { "width": 800, "height": 480 },
  "background": "background.png",
  "states": {
    "idle": {
      "sheet": "idle.png",
      "mode": "grid",
      "frame_width": 128,
      "frame_height": 128,
      "columns": 8,
      "frame_count": 8,
      "position": { "x": 336, "y": 176 },
      "scale": 2
    },
    "working": {
      "sheet": "working.png",
      "mode": "frames",
      "frames": [
        { "x": 0, "y": 0, "w": 120, "h": 140 },
        { "x": 128, "y": 0, "w": 132, "h": 144 }
      ],
      "position": { "x": 330, "y": 170 },
      "scale": 2
    }
  }
}
```

The processor fails with clear errors for missing states, missing files, invalid frame dimensions, or invalid coordinates. These failures happen during asset processing, not while the avatar is running.

## Testing

Add focused tests for:

- status classification in the OpenClaw server companion
- HTTP poller behavior for valid, invalid, timeout, stale, and unknown-state responses
- state file writes with configurable paths
- manifest parsing and spritesheet frame extraction

Keep renderer tests light unless renderer behavior changes.
