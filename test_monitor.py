import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from PIL import Image
from pi_avatar import http_monitor
from pi_avatar import openclaw_status
from pi_avatar.constants import WORKING_CPU_THRESHOLD
from pi_avatar.config import load_config
from pi_avatar.state import StateWriter
import renderer
from pi_avatar import assets as avatar_assets


REPO_ROOT = Path(__file__).resolve().parent


class MonitorTests(unittest.TestCase):
    def setUp(self):
        openclaw_status.last_error_time = 0
        openclaw_status.last_success_time = 0
        openclaw_status.last_thinking_time = 0

    def test_write_state_updates_when_detail_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            writer = StateWriter(state_file)

            writer.write("working", "first command")
            first = json.loads(state_file.read_text())

            writer.write("working", "second command")
            second = json.loads(state_file.read_text())

        self.assertEqual(first["state"], "working")
        self.assertEqual(second["state"], "working")
        self.assertEqual(second["detail"], "second command")

    def test_load_config_uses_portable_defaults(self):
        config = load_config(env={})

        self.assertEqual(config.state_file, Path("/var/lib/pi-avatar/state.json"))
        self.assertEqual(config.asset_dir, Path("/opt/pi-avatar/assets"))
        self.assertEqual(config.env_file, Path("/etc/pi-avatar/avatar.env"))

    def test_load_config_allows_environment_overrides(self):
        env = {
            "STATE_FILE": "/tmp/avatar-state.json",
            "ASSET_DIR": "/tmp/avatar-assets",
            "STATUS_URL": "http://openclaw.example:18888/status",
        }

        config = load_config(env=env)

        self.assertEqual(config.state_file, Path("/tmp/avatar-state.json"))
        self.assertEqual(config.asset_dir, Path("/tmp/avatar-assets"))
        self.assertEqual(config.status_url, "http://openclaw.example:18888/status")

    def test_state_writer_skips_unchanged_payloads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            writer = StateWriter(state_file)

            self.assertTrue(writer.write("idle", "ready"))
            first_updated = json.loads(state_file.read_text())["updated"]

            self.assertFalse(writer.write("idle", "ready"))
            second_updated = json.loads(state_file.read_text())["updated"]

        self.assertEqual(first_updated, second_updated)

    def test_incremental_file_reader_returns_only_new_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            log_file.write_text("old line\n")

            reader = openclaw_status.IncrementalFileReader(log_file)
            self.assertEqual(reader.read_new(), "")

            log_file.write_text("old line\nnew line\n")
            self.assertEqual(reader.read_new(), "new line\n")
            self.assertEqual(reader.read_new(), "")

    def test_classify_new_logs_does_not_reuse_stale_error_lines(self):
        with mock.patch.object(openclaw_status.time, "time", return_value=100.0):
            state, detail = openclaw_status.classify_from_logs("error: failed pairing")

        self.assertEqual(state, "error")
        self.assertIn("error", detail.lower())

        with mock.patch.object(openclaw_status.time, "time", return_value=200.0):
            state, detail = openclaw_status.classify_from_logs("")

        self.assertEqual(state, "idle")
        self.assertIn("running", detail.lower())

    def test_choose_state_gives_health_priority_over_activity(self):
        state, detail = openclaw_status.choose_state(
            health_state=("offline", "service stopped"),
            log_state=("working", "tool call"),
            cpu=99.0,
        )

        self.assertEqual(state, "offline")
        self.assertEqual(detail, "service stopped")

    def test_choose_state_uses_cpu_as_idle_fallback(self):
        state, detail = openclaw_status.choose_state(
            health_state=None,
            log_state=("idle", "OpenClaw gateway is running"),
            cpu=WORKING_CPU_THRESHOLD,
        )

        self.assertEqual(state, "working")
        self.assertIn("CPU", detail)

    def test_openclaw_status_builds_offline_payload_when_service_inactive(self):
        with mock.patch.object(openclaw_status, "service_active", return_value=False):
            payload = openclaw_status.build_status(load_config(env={}), cpu=0.0, logs="")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["state"], "offline")
        self.assertIn("service", payload)
        self.assertFalse(payload["service"]["active"])

    def test_openclaw_status_builds_error_payload_when_port_missing(self):
        with (
            mock.patch.object(openclaw_status, "service_active", return_value=True),
            mock.patch.object(openclaw_status, "gateway_port_listening", return_value=False),
            mock.patch.object(openclaw_status, "recent_config_audit_error", return_value=None),
        ):
            payload = openclaw_status.build_status(load_config(env={}), cpu=0.0, logs="")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["state"], "error")
        self.assertFalse(payload["service"]["port_listening"])

    def test_openclaw_status_builds_working_payload_from_logs(self):
        with (
            mock.patch.object(openclaw_status, "service_active", return_value=True),
            mock.patch.object(openclaw_status, "gateway_port_listening", return_value=True),
            mock.patch.object(openclaw_status, "recent_config_audit_error", return_value=None),
        ):
            payload = openclaw_status.build_status(load_config(env={}), cpu=0.0, logs="calling tool")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["state"], "working")
        self.assertEqual(payload["service"]["cpu_percent"], 0.0)

    def test_openclaw_describe_payload_reports_service_health(self):
        payload = {
            "ok": True,
            "state": "idle",
            "detail": "OpenClaw gateway is running",
            "service": {
                "active": True,
                "port_listening": True,
                "cpu_percent": 2.5,
            },
        }

        result = openclaw_status.describe_status_payload(payload)

        self.assertEqual(result.health, "ok")
        self.assertEqual(result.state, "idle")
        self.assertIn("active=True", result.message)
        self.assertIn("port_listening=True", result.message)
        self.assertIn("cpu=2.5%", result.message)

    def test_status_sampler_logs_only_when_payload_status_changes(self):
        config = load_config(env={})
        output = []

        with (
            mock.patch.object(openclaw_status, "IncrementalFileReader", return_value=mock.Mock(read_new=lambda: "")),
            mock.patch.object(openclaw_status, "JournalFollower", return_value=mock.Mock(read_new=lambda: "", close=lambda: None)),
            mock.patch.object(openclaw_status, "check_health", return_value=(None, True, True)),
            mock.patch.object(openclaw_status, "get_openclaw_cpu_percent", return_value=0.0),
        ):
            sampler = openclaw_status.StatusSampler(config, log_func=output.append)
            sampler.sample()
            sampler.sample()

        self.assertEqual(len(output), 1)
        self.assertIn("status: ok", output[0])

    def test_http_status_to_state_accepts_fresh_known_state(self):
        payload = {
            "state": "success",
            "detail": "done",
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        state, detail = http_monitor.status_to_state(
            payload,
            now=datetime.now(timezone.utc),
            stale_seconds=15,
        )

        self.assertEqual(state, "success")
        self.assertEqual(detail, "done")

    def test_http_status_to_state_rejects_unknown_state(self):
        payload = {
            "state": "dancing",
            "detail": "unknown",
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

        state, detail = http_monitor.status_to_state(
            payload,
            now=datetime.now(timezone.utc),
            stale_seconds=15,
        )

        self.assertEqual(state, "offline")
        self.assertIn("Unknown", detail)

    def test_http_status_to_state_rejects_stale_timestamp(self):
        payload = {
            "state": "working",
            "detail": "old",
            "updated": (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(timespec="seconds"),
        }

        state, detail = http_monitor.status_to_state(
            payload,
            now=datetime.now(timezone.utc),
            stale_seconds=15,
        )

        self.assertEqual(state, "offline")
        self.assertIn("stale", detail.lower())

    def test_fetch_status_rejects_invalid_json(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"not json"

        with mock.patch.object(http_monitor.request, "urlopen", return_value=FakeResponse()):
            payload, error = http_monitor.fetch_status(load_config(env={}))

        self.assertIsNone(payload)
        self.assertIn("Invalid JSON", error)

    def test_describe_poll_result_reports_connected_status_url(self):
        payload = {
            "state": "working",
            "detail": "tool call",
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        config = load_config(env={"STATUS_URL": "http://server.example/status"})

        result = http_monitor.describe_poll_result(config, payload=payload, error_message=None)

        self.assertEqual(result.health, "connected")
        self.assertEqual(result.state, "working")
        self.assertIn("http://server.example/status", result.message)
        self.assertIn("tool call", result.message)

    def test_describe_poll_result_reports_fetch_error(self):
        config = load_config(env={"STATUS_URL": "http://server.example/status"})

        result = http_monitor.describe_poll_result(config, payload=None, error_message="Status feed unavailable")

        self.assertEqual(result.health, "offline")
        self.assertEqual(result.state, "offline")
        self.assertIn("Status feed unavailable", result.message)

    def test_transition_logger_logs_only_when_status_changes(self):
        output = []
        logger = http_monitor.TransitionLogger(output.append)
        result = http_monitor.PollResult("connected", "idle", "connected to server")

        self.assertTrue(logger.log_if_changed(result))
        self.assertFalse(logger.log_if_changed(result))
        self.assertEqual(output, ["connected to server"])

    def test_renderer_read_state_uses_configured_state_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps({"state": "thinking", "detail": "remote"}))
            config = load_config(env={"STATE_FILE": str(state_file)})

            state, detail = renderer.read_state(config)

        self.assertEqual(state, "thinking")
        self.assertEqual(detail, "remote")

    def test_renderer_read_state_rejects_unknown_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps({"state": "surprised", "detail": "remote"}))
            config = load_config(env={"STATE_FILE": str(state_file)})

            state, detail = renderer.read_state(config)

        self.assertEqual(state, "idle")
        self.assertEqual(detail, "Unknown state")

    def test_renderer_defaults_to_kmsdrm_without_desktop_display(self):
        env = {}

        renderer.configure_sdl_environment(env)

        self.assertEqual(env["SDL_FBDEV"], "/dev/fb0")
        self.assertEqual(env["SDL_VIDEODRIVER"], "kmsdrm")

    def test_renderer_preserves_explicit_sdl_video_driver(self):
        env = {"SDL_VIDEODRIVER": "dummy"}

        renderer.configure_sdl_environment(env)

        self.assertEqual(env["SDL_VIDEODRIVER"], "dummy")

    def test_renderer_leaves_desktop_video_driver_selection_to_sdl(self):
        env = {"DISPLAY": ":0"}

        renderer.configure_sdl_environment(env)

        self.assertNotIn("SDL_VIDEODRIVER", env)

    def test_pack_framebuffer_image_uses_framebuffer_bitfields(self):
        image = Image.new("RGB", (2, 1))
        image.putpixel((0, 0), (255, 0, 0))
        image.putpixel((1, 0), (0, 0, 255))
        info = renderer.FramebufferInfo(
            width=2,
            height=1,
            bits_per_pixel=32,
            line_length=8,
            red=renderer.BitField(offset=16, length=8),
            green=renderer.BitField(offset=8, length=8),
            blue=renderer.BitField(offset=0, length=8),
            transp=renderer.BitField(offset=24, length=8),
        )

        packed = renderer.pack_framebuffer_image(image, info)

        self.assertEqual(packed, b"\x00\x00\xff\x00\xff\x00\x00\x00")

    def test_pack_framebuffer_image_respects_line_padding(self):
        image = Image.new("RGB", (1, 2), (255, 255, 255))
        info = renderer.FramebufferInfo(
            width=1,
            height=2,
            bits_per_pixel=16,
            line_length=4,
            red=renderer.BitField(offset=11, length=5),
            green=renderer.BitField(offset=5, length=6),
            blue=renderer.BitField(offset=0, length=5),
            transp=renderer.BitField(offset=0, length=0),
        )

        packed = renderer.pack_framebuffer_image(image, info)

        self.assertEqual(packed, b"\xff\xff\x00\x00\xff\xff\x00\x00")

    def test_process_assets_extracts_grid_frames_to_full_canvas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            output = Path(tmpdir) / "assets"
            source.mkdir()

            Image.new("RGB", (4, 4), (10, 20, 30)).save(source / "background.png")
            sheet = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
            sheet.paste((255, 0, 0, 255), (0, 0, 2, 2))
            sheet.paste((0, 255, 0, 255), (2, 0, 4, 2))
            sheet.save(source / "idle.png")

            manifest = {
                "canvas": {"width": 4, "height": 4},
                "background": "background.png",
                "states": {
                    "idle": {
                        "sheet": "idle.png",
                        "mode": "grid",
                        "frame_width": 2,
                        "frame_height": 2,
                        "columns": 2,
                        "frame_count": 2,
                        "position": {"x": 1, "y": 1},
                    }
                },
            }

            avatar_assets.process_manifest(manifest, source, output)

            first = Image.open(output / "idle" / "00.png")
            second = Image.open(output / "idle" / "01.png")

        self.assertEqual(first.size, (4, 4))
        self.assertEqual(first.getpixel((1, 1))[:3], (255, 0, 0))
        self.assertEqual(second.getpixel((1, 1))[:3], (0, 255, 0))

    def test_process_assets_extracts_explicit_variable_frames(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            output = Path(tmpdir) / "assets"
            source.mkdir()

            Image.new("RGB", (5, 5), (1, 2, 3)).save(source / "background.png")
            sheet = Image.new("RGBA", (5, 3), (0, 0, 0, 0))
            sheet.paste((0, 0, 255, 255), (0, 0, 1, 1))
            sheet.paste((255, 255, 0, 255), (1, 0, 4, 3))
            sheet.save(source / "working.png")

            manifest = {
                "canvas": {"width": 5, "height": 5},
                "background": "background.png",
                "states": {
                    "working": {
                        "sheet": "working.png",
                        "mode": "frames",
                        "frames": [
                            {"x": 0, "y": 0, "w": 1, "h": 1},
                            {"x": 1, "y": 0, "w": 3, "h": 3},
                        ],
                        "position": {"x": 1, "y": 1},
                    }
                },
            }

            avatar_assets.process_manifest(manifest, source, output)

            first = Image.open(output / "working" / "00.png")
            second = Image.open(output / "working" / "01.png")

        self.assertEqual(first.getpixel((1, 1))[:3], (0, 0, 255))
        self.assertEqual(second.getpixel((3, 3))[:3], (255, 255, 0))

    def test_pi_installer_uses_virtual_environment_for_dependencies_and_services(self):
        installer = (REPO_ROOT / "scripts" / "install-pi.sh").read_text()
        monitor_service = (REPO_ROOT / "systemd" / "pi-avatar-monitor.service").read_text()
        renderer_service = (REPO_ROOT / "systemd" / "pi-avatar-renderer.service").read_text()

        self.assertIn("VENV_DIR=", installer)
        self.assertIn("python3 -m venv", installer)
        self.assertIn('"${VENV_DIR}/bin/python" -m pip install', installer)
        self.assertIn("ExecStart=/opt/pi-avatar/.venv/bin/python /opt/pi-avatar/monitor.py", monitor_service)
        self.assertIn("ExecStart=/opt/pi-avatar/.venv/bin/python /opt/pi-avatar/renderer.py", renderer_service)
        self.assertIn("RuntimeDirectory=pi-avatar", renderer_service)
        self.assertIn("RuntimeDirectoryMode=0700", renderer_service)
        self.assertIn("Environment=XDG_RUNTIME_DIR=/run/pi-avatar", renderer_service)
        self.assertIn("Environment=SDL_VIDEODRIVER=kmsdrm", renderer_service)
        self.assertIn("ExecStartPre=/bin/sh -c '/usr/bin/setterm --cursor off --blank 0 --powerdown 0 > /dev/tty1'", renderer_service)
        self.assertIn("ExecStopPost=/bin/sh -c '/usr/bin/setterm --cursor on > /dev/tty1'", renderer_service)

    def test_openclaw_installer_uses_virtual_environment_for_dependencies_and_service(self):
        installer = (REPO_ROOT / "scripts" / "install-openclaw-status-agent.sh").read_text()
        service = (REPO_ROOT / "systemd" / "openclaw-avatar-status.service").read_text()

        self.assertIn("VENV_DIR=", installer)
        self.assertIn("python3 -m venv", installer)
        self.assertNotIn("requirements.txt", installer)
        self.assertNotIn("pip install", installer)
        self.assertIn("ExecStart=/opt/pi-avatar/.venv/bin/python /opt/pi-avatar/status_agent.py", service)


if __name__ == "__main__":
    unittest.main()
