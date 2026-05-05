# Remote OpenClaw Avatar Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the avatar monitor into a Pi-side HTTP poller and an OpenClaw-server status feed, add portable installers, and add a spritesheet asset pipeline.

**Architecture:** Move shared state/config/constants into a small `pi_avatar` package. Run `openclaw-avatar-status` on the OpenClaw server to classify local service/log/CPU health and expose JSON. Run `pi-avatar-monitor` on the Pi to poll that JSON and write renderer state, while the renderer continues to display prepared full-screen frames.

**Tech Stack:** Python 3 standard library HTTP server/client, `pygame` for rendering, Pillow for asset processing, systemd units, shell install scripts, `unittest`.

---

## Chunk 1: Package Skeleton, Config, and State

### Task 1: Introduce Package and Shared State Helpers

**Files:**
- Create: `pi_avatar/__init__.py`
- Create: `pi_avatar/constants.py`
- Create: `pi_avatar/config.py`
- Create: `pi_avatar/state.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write tests for configurable state writes and env config**

Add tests that patch `os.environ` and verify:
- `load_config()` defaults to `/var/lib/pi-avatar/state.json`, `/opt/pi-avatar/assets`, and `/etc/pi-avatar/avatar.env`.
- env vars override `STATE_FILE`, `ASSET_DIR`, and `STATUS_URL`.
- `write_state()` writes atomically and skips unchanged state/detail payloads.

Run: `python3 -m unittest test_monitor.py`
Expected: FAIL because `pi_avatar.config` and `pi_avatar.state` do not exist.

- [ ] **Step 2: Implement package helpers**

Create:
- `pi_avatar/constants.py` with valid states, default state, default ports, poll intervals, thresholds, and hold durations.
- `pi_avatar/config.py` with a `Config` dataclass and `load_config(env=os.environ)` helper.
- `pi_avatar/state.py` with `now_iso()` and `StateWriter`.

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest test_monitor.py`
Expected: PASS.

## Chunk 2: OpenClaw Status Agent

### Task 2: Extract Local OpenClaw Observation and Serve HTTP

**Files:**
- Create: `pi_avatar/openclaw_status.py`
- Create: `status_agent.py`
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write status classification tests**

Add tests for:
- service inactive -> `offline`
- service active but port missing -> `error`
- config audit warning -> `error`
- error/success/working/thinking log terms
- CPU fallback to `working` and `thinking`
- JSON payload includes `ok`, `state`, `detail`, `updated`, and `service`

Run: `python3 -m unittest test_monitor.py`
Expected: FAIL until status code is extracted.

- [ ] **Step 2: Move existing local monitoring logic**

Move local command/log classification from `monitor.py` into `pi_avatar/openclaw_status.py`:
- `run_command`
- incremental log readers
- journal follower
- service/port/process/CPU checks
- config audit check
- log classification
- status payload builder

Keep behavior equivalent to the current monitor.

- [ ] **Step 3: Add HTTP server entrypoint**

Create `status_agent.py` with:
- `GET /status` returning status JSON
- `GET /healthz` returning a simple OK payload
- configurable bind host/port from env
- non-200 for unknown paths

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest test_monitor.py`
Expected: PASS.

## Chunk 3: Pi HTTP Poller

### Task 3: Replace Local Monitor With HTTP Poller

**Files:**
- Create: `pi_avatar/http_monitor.py`
- Modify: `monitor.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write HTTP poller tests**

Add tests for:
- valid status response writes reported state/detail
- timeout/unavailable endpoint writes `offline`
- invalid JSON writes `offline`
- unknown state writes `offline`
- stale timestamp writes `offline`

Use local fake response objects or monkeypatch `urllib.request.urlopen`; do not require network.

Run: `python3 -m unittest test_monitor.py`
Expected: FAIL until HTTP poller exists.

- [ ] **Step 2: Implement poller**

Create `pi_avatar/http_monitor.py` with:
- `fetch_status(config)`
- `validate_remote_status(payload, now)`
- `status_to_state(payload)`
- `run_monitor(config)`

Rewrite top-level `monitor.py` as a thin entrypoint that loads config and runs the HTTP monitor.

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest test_monitor.py`
Expected: PASS.

## Chunk 4: Renderer Path Cleanup

### Task 4: Use Shared Config in Renderer

**Files:**
- Modify: `renderer.py`
- Modify: `test_monitor.py`

- [ ] **Step 1: Add renderer config tests where practical**

Add light tests for invalid state fallback and configured asset/state paths without initializing a display.

Run: `python3 -m unittest test_monitor.py`
Expected: FAIL until renderer uses package constants/config.

- [ ] **Step 2: Update renderer imports and paths**

Update `renderer.py` to use:
- `pi_avatar.constants.VALID_STATES`
- `pi_avatar.constants.DEFAULT_STATE`
- `load_config()` for state file and asset directory defaults

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest test_monitor.py`
Expected: PASS.

## Chunk 5: Spritesheet Asset Pipeline

### Task 5: Add Manifest-Driven Asset Processor

**Files:**
- Create: `pi_avatar/assets.py`
- Create: `process_assets.py`
- Create: `source-assets/manifest.example.json`
- Modify: `test_monitor.py`

- [ ] **Step 1: Write asset processing tests**

Create small temporary Pillow images and verify:
- `grid` mode extracts frames in filename order
- `frames` mode extracts explicit variable-sized rectangles
- output files are full canvas size
- missing files and invalid coordinates fail clearly

Run: `python3 -m unittest test_monitor.py`
Expected: FAIL until asset processor exists.

- [ ] **Step 2: Implement asset processor**

Create manifest parser and processor that:
- loads `background`
- validates `canvas`
- supports `grid` and `frames`
- applies `scale`
- places frames at `position`
- writes `assets/<state>/<index>.png`

- [ ] **Step 3: Add CLI**

Create `process_assets.py` with arguments:
- `--source source-assets`
- `--output assets`
- `--manifest manifest.json`

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest test_monitor.py`
Expected: PASS.

## Chunk 6: Packaging and Documentation

### Task 6: Add Installers, Units, Requirements, and README

**Files:**
- Create: `requirements.txt`
- Create: `systemd/pi-avatar-renderer.service`
- Create: `systemd/pi-avatar-monitor.service`
- Create: `systemd/openclaw-avatar-status.service`
- Create: `scripts/install-pi.sh`
- Create: `scripts/install-openclaw-status-agent.sh`
- Create: `README.md`

- [ ] **Step 1: Add packaging files**

Installers should:
- create `/opt/pi-avatar`, `/etc/pi-avatar`, and `/var/lib/pi-avatar`
- copy app files and assets
- install Python deps from `requirements.txt`
- install systemd units
- write config template only if missing
- run `systemctl daemon-reload`

- [ ] **Step 2: Add documentation**

Document:
- Pi install
- OpenClaw server status agent install
- required config values
- status endpoint example
- asset manifest and processing command
- service management commands

- [ ] **Step 3: Final verification**

Run:
- `python3 -m unittest test_monitor.py`
- `python3 -m py_compile monitor.py renderer.py status_agent.py process_assets.py pi_avatar/*.py`

Expected: PASS.
