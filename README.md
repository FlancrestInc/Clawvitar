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

The renderer does not read spritesheets at runtime. It reads prebuilt full-screen PNG frames from:

```text
assets/<state>/00.png
assets/<state>/01.png
...
```

Use `process_assets.py` whenever you want to turn source art in `source-assets/` into those deployable frames.

### 1. Know the Avatar States

The supported state folder names are:

```text
booting
idle
thinking
working
success
error
offline
```

Each state can have any number of frames. The renderer loops those frames at the per-state frame rate defined in `pi_avatar/constants.py`.

### 2. Prepare Source Files

Put source art in `source-assets/`:

```text
source-assets/
  background.png
  manifest.json
  idle.png
  thinking.png
  working.png
  success.png
  error.png
  offline.png
  booting.png
```

`background.png` should be the full screen background. It will be resized to the manifest canvas size.

Each state spritesheet should be a transparent PNG if you want the background to show through. Opaque spritesheets work too, but they will cover the background where placed.

### 3. Create The Manifest

Start from the example:

```bash
cp source-assets/manifest.example.json source-assets/manifest.json
```

The top-level fields are:

```json
{
  "canvas": { "width": 800, "height": 480 },
  "background": "background.png",
  "states": {}
}
```

`canvas` should match the display target. Current renderer defaults are `800x480`.

`background` is relative to `source-assets/`.

`states` maps each avatar state to a spritesheet extraction rule.

### 4. Use Grid Mode For Even Spritesheets

Use `mode: "grid"` when every frame is the same size and arranged in rows/columns.

```json
"idle": {
  "sheet": "idle.png",
  "mode": "grid",
  "frame_width": 128,
  "frame_height": 128,
  "columns": 8,
  "frame_count": 8,
  "position": { "x": 336, "y": 176 },
  "scale": 2
}
```

Fields:

- `sheet`: spritesheet filename under `source-assets/`.
- `frame_width` / `frame_height`: source rectangle size for each frame.
- `columns`: how many frames per row.
- `frame_count`: total frames to extract.
- `position`: where to place the extracted sprite on the full-screen canvas.
- `scale`: optional multiplier. Defaults to `1`. Uses nearest-neighbor scaling for pixel art.

Frame extraction starts at the top-left of the sheet, moves left to right, then continues on the next row.

### 5. Use Frames Mode For Uneven Spritesheets

Use `mode: "frames"` when each frame needs a custom rectangle.

```json
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
```

Each frame rectangle is in source spritesheet pixels. The same `position` and `scale` are applied to every extracted frame for that state.

### 6. Generate Runtime Frames

From the repo root:

```bash
python3 process_assets.py --source source-assets --output assets --manifest manifest.json
```

If `--manifest` does not contain a slash, it is resolved inside the source directory, so this reads:

```text
source-assets/manifest.json
```

The output will look like:

```text
assets/
  idle/
    00.png
    01.png
  working/
    00.png
    01.png
```

Existing files with the same frame names are overwritten. If you reduce a state's frame count, remove extra old frames from that `assets/<state>/` folder.

### 7. Preview The Generated Art

Open the generated PNGs directly:

```bash
xdg-open assets/idle/00.png
```

Or quickly inspect dimensions:

```bash
python3 - <<'PY'
from pathlib import Path
from PIL import Image

for path in sorted(Path("assets").glob("*/*.png")):
    with Image.open(path) as image:
        print(path, image.size)
PY
```

Every generated frame should match the canvas size, usually `800x480`.

### 8. Deploy Updated Art To The Pi

After regenerating `assets/`, copy or sync the repo to the Pi and rerun:

```bash
sudo ./scripts/install-pi.sh
sudo systemctl restart pi-avatar-renderer
```

The installer copies `assets/` into `/opt/pi-avatar/assets`.

### 9. Generate Placeholder Art

`make_test_assets.py` creates simple placeholder full-screen frames directly under `/opt/pi-avatar/assets`.

On the Pi:

```bash
sudo python3 make_test_assets.py
sudo systemctl restart pi-avatar-renderer
```

This is useful for proving the renderer works, but it is not the spritesheet pipeline. For real art, prefer `source-assets/manifest.json` plus `process_assets.py`.

### Troubleshooting Assets

- `Missing background`: confirm `background` points to a file under `source-assets/`.
- `Missing spritesheet`: confirm each state's `sheet` filename exists under `source-assets/`.
- `grid frame ... is outside the spritesheet`: check `frame_width`, `frame_height`, `columns`, and `frame_count`.
- Sprite appears in the wrong place: adjust `position.x` and `position.y`.
- Sprite is too large or small: adjust `scale`.
- Old animation frames still appear: delete stale files in `assets/<state>/` after lowering `frame_count`.
- Renderer shows offline art: check `/var/lib/pi-avatar/state.json`; that means monitor status, not asset processing.

## Development

Run tests:

```bash
python3 -m unittest test_monitor.py
```

Compile-check entrypoints:

```bash
python3 -m py_compile monitor.py renderer.py status_agent.py process_assets.py pi_avatar/*.py
```
