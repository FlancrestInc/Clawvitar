import json
import os
import select
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .constants import (
    CONFIG_ERROR_WINDOW_SECONDS,
    CPU_POLL_SECONDS,
    ERROR_HOLD_SECONDS,
    HEALTH_POLL_SECONDS,
    LOG_LOOKBACK_LINES,
    SUCCESS_HOLD_SECONDS,
    THINKING_CPU_THRESHOLD,
    THINKING_HOLD_SECONDS,
    WORKING_CPU_THRESHOLD,
)
from .state import now_iso

last_error_time = 0
last_success_time = 0
last_thinking_time = 0


@dataclass(frozen=True)
class StatusDescription:
    health: str
    state: str
    message: str


class TransitionLogger:
    def __init__(self, log_func=None):
        self.log_func = log_func or self._print
        self.last_key = None

    @staticmethod
    def _print(message):
        print(message, flush=True)

    def log_if_changed(self, description):
        key = (description.health, description.state, description.message)
        if key == self.last_key:
            return False

        self.log_func(description.message)
        self.last_key = key
        return True


def run_command(args, timeout=5):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None


class IncrementalFileReader:
    def __init__(self, path, start_at_end=True):
        self.path = Path(path)
        self.offset = 0
        self.inode = None

        if start_at_end:
            self._seek_to_end()

    def _stat(self):
        try:
            return self.path.stat()
        except OSError:
            return None

    def _seek_to_end(self):
        stat = self._stat()
        if stat is None:
            self.offset = 0
            self.inode = None
            return

        self.offset = stat.st_size
        self.inode = stat.st_ino

    def read_new(self):
        stat = self._stat()
        if stat is None:
            self.offset = 0
            self.inode = None
            return ""

        if self.inode is None:
            self.inode = stat.st_ino
        elif stat.st_ino != self.inode:
            self.inode = stat.st_ino
            self.offset = 0

        if stat.st_size < self.offset:
            self.offset = 0

        if stat.st_size == self.offset:
            return ""

        try:
            with self.path.open("rb") as file:
                file.seek(self.offset)
                data = file.read()
                self.offset = file.tell()
        except OSError:
            return ""

        return data.decode(errors="replace")


class JournalFollower:
    def __init__(self, service):
        self.service = service
        self.process = None
        self._start()

    def _start(self):
        try:
            self.process = subprocess.Popen(
                [
                    "journalctl",
                    "-u",
                    self.service,
                    "--no-pager",
                    "-n",
                    "0",
                    "-f",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            os.set_blocking(self.process.stdout.fileno(), False)
        except Exception:
            self.process = None

    def read_new(self):
        if self.process is None or self.process.stdout is None:
            return ""

        if self.process.poll() is not None:
            self._start()
            return ""

        chunks = []
        fd = self.process.stdout.fileno()

        while True:
            readable, _, _ = select.select([fd], [], [], 0)
            if not readable:
                break

            try:
                chunk = os.read(fd, 8192)
            except BlockingIOError:
                break
            except OSError:
                return ""

            if not chunk:
                break

            chunks.append(chunk)

        if not chunks:
            return ""

        return b"".join(chunks).decode(errors="replace")

    def close(self):
        if self.process is None:
            return

        try:
            self.process.terminate()
        except Exception:
            pass


def service_active(config):
    result = run_command(["systemctl", "is-active", config.openclaw_service])
    return result is not None and result.stdout.strip() == "active"


def gateway_port_listening(config):
    result = run_command(["ss", "-ltnp"], timeout=5)

    if result is None or result.returncode != 0:
        return False

    return f":{config.openclaw_port}" in result.stdout


def get_service_main_pid(config):
    result = run_command(["systemctl", "show", config.openclaw_service, "-p", "MainPID", "--value"])

    if result is None or result.returncode != 0:
        return None

    raw = result.stdout.strip()

    if not raw or raw == "0":
        return None

    return raw


def get_gateway_port_pid(config):
    result = run_command(["ss", "-ltnp"], timeout=5)

    if result is None or result.returncode != 0:
        return None

    port_token = f":{config.openclaw_port}"
    for line in result.stdout.splitlines():
        if port_token not in line:
            continue

        marker = "pid="
        if marker not in line:
            return None

        pid = line.split(marker, 1)[1].split(",", 1)[0].strip()
        return pid or None

    return None


def get_process_tree_pids(root_pid):
    if not root_pid:
        return []

    result = run_command(["pgrep", "-P", str(root_pid)], timeout=5)

    pids = [str(root_pid)]

    if result is not None and result.returncode == 0:
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                pids.append(line)

    return pids


def get_openclaw_cpu_percent(config):
    root_pid = get_service_main_pid(config) or get_gateway_port_pid(config)
    pids = get_process_tree_pids(root_pid)

    if not pids:
        return 0.0

    result = run_command(["ps", "-p", ",".join(pids), "-o", "pcpu="], timeout=5)

    if result is None or result.returncode != 0:
        return 0.0

    total = 0.0

    for line in result.stdout.splitlines():
        try:
            total += float(line.strip())
        except ValueError:
            pass

    return total


def read_tail(path, line_count):
    path = Path(path)
    if not path.exists():
        return ""

    try:
        lines = path.read_text(errors="replace").splitlines()
        return "\n".join(lines[-line_count:]).lower()
    except Exception:
        return ""


def read_journal_tail(config):
    result = run_command(
        [
            "journalctl",
            "-u",
            config.openclaw_service,
            "--no-pager",
            "-n",
            str(LOG_LOOKBACK_LINES),
        ],
        timeout=8,
    )

    if result is None:
        return ""

    return (result.stdout + "\n" + result.stderr).lower()


def read_recent_logs(config):
    runtime_log = read_tail(config.runtime_log, LOG_LOOKBACK_LINES)
    journal_log = read_journal_tail(config)

    return f"{runtime_log}\n{journal_log}"


def read_new_logs(runtime_reader, journal_follower):
    runtime_log = runtime_reader.read_new() if runtime_reader else ""
    journal_log = journal_follower.read_new() if journal_follower else ""

    return f"{runtime_log}\n{journal_log}".lower()


def recent_config_audit_error(config):
    if not config.config_audit_log.exists():
        return None

    try:
        lines = config.config_audit_log.read_text(errors="replace").splitlines()[-10:]
    except Exception:
        return None

    current_time = time.time()

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue

        ts = entry.get("ts")
        suspicious = entry.get("suspicious") or []
        valid = entry.get("valid")

        if not ts:
            continue

        try:
            event_time = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue

        age = current_time - event_time

        if age > CONFIG_ERROR_WINDOW_SECONDS:
            continue

        if valid is False or suspicious:
            return "Recent OpenClaw config audit warning"

    return None


def classify_from_logs(logs):
    global last_error_time, last_success_time, last_thinking_time

    current_time = time.time()

    error_terms = [
        "error",
        "exception",
        "failed",
        "failure",
        "pairing required",
        "not verified",
        "unauthorized",
        "connection refused",
        "cannot connect",
        "timeout",
        "econnrefused",
        "enotfound",
        "stack trace",
    ]

    success_terms = [
        "completed",
        "complete",
        "finished",
        "success",
        "done",
        "task finished",
        "tool result",
    ]

    working_terms = [
        "executing",
        "running task",
        "processing",
        "invoking",
        "calling tool",
        "tool call",
        "workspace",
        "started task",
        "command",
        "shell",
    ]

    thinking_terms = [
        "agent",
        "assistant",
        "thinking",
        "planning",
        "model",
        "prompt",
        "message received",
        "request",
    ]

    if logs:
        if any(term in logs for term in error_terms):
            last_error_time = current_time
            return "error", "Recent OpenClaw error-like log entry"

        if any(term in logs for term in success_terms):
            last_success_time = current_time
            return "success", "Recent OpenClaw completion-like log entry"

        if any(term in logs for term in working_terms):
            return "working", "Recent OpenClaw tool/work activity"

        if any(term in logs for term in thinking_terms):
            last_thinking_time = current_time
            return "thinking", "Recent OpenClaw agent activity"

    if current_time - last_error_time < ERROR_HOLD_SECONDS:
        return "error", "Holding recent error state"

    if current_time - last_success_time < SUCCESS_HOLD_SECONDS:
        return "success", "Holding recent success state"

    if current_time - last_thinking_time < THINKING_HOLD_SECONDS:
        return "thinking", "Holding recent thinking state"

    return "idle", "OpenClaw gateway is running"


def check_health(config):
    active = service_active(config)
    port_listening = gateway_port_listening(config)

    if not active and not port_listening:
        return ("offline", f"{config.openclaw_service} is not active and port {config.openclaw_port} is not listening"), False, False

    if not port_listening:
        return ("error", f"OpenClaw service active, but port {config.openclaw_port} is not listening"), True, False

    config_error = recent_config_audit_error(config)
    if config_error:
        return ("error", config_error), True, True

    return None, active or port_listening, True


def choose_state(health_state, log_state, cpu):
    if health_state:
        return health_state

    state, detail = log_state or ("idle", "OpenClaw gateway is running")

    if state == "idle":
        if cpu >= WORKING_CPU_THRESHOLD:
            return "working", f"OpenClaw CPU activity detected: {cpu:.1f}%"
        if cpu >= THINKING_CPU_THRESHOLD:
            return "thinking", f"Light OpenClaw activity detected: {cpu:.1f}%"

    return state, detail


def build_status(config, cpu=None, logs=None):
    health_state, active, port_listening = check_health(config)

    if cpu is None:
        cpu = get_openclaw_cpu_percent(config) if active else 0.0

    if logs is None:
        logs = read_recent_logs(config)

    state, detail = choose_state(health_state, classify_from_logs(logs), cpu)

    return {
        "ok": state not in ("offline", "error"),
        "state": state,
        "detail": detail,
        "updated": now_iso(),
        "service": {
            "active": bool(active),
            "port_listening": bool(port_listening),
            "cpu_percent": float(cpu),
        },
    }


def describe_status_payload(payload):
    service = payload.get("service", {})
    health = "ok" if payload.get("ok") else "not-ok"
    state = payload.get("state", "unknown")
    detail = payload.get("detail", "")
    active = service.get("active")
    port_listening = service.get("port_listening")
    cpu = float(service.get("cpu_percent") or 0.0)

    detail_suffix = f": {detail}" if detail else ""
    return StatusDescription(
        health=health,
        state=state,
        message=(
            f"status: {health} -> {state}{detail_suffix} "
            f"(active={active}, port_listening={port_listening}, cpu={cpu:.1f}%)"
        ),
    )


class StatusSampler:
    def __init__(self, config, log_func=None):
        self.config = config
        self.runtime_reader = IncrementalFileReader(config.runtime_log)
        self.journal_follower = JournalFollower(config.openclaw_service)
        self.transition_logger = TransitionLogger(log_func)
        self.health_state = None
        self.active = False
        self.port_listening = False
        self.cpu = 0.0
        self.last_health_check = 0
        self.last_cpu_check = 0

    def sample(self):
        current_time = time.time()

        if current_time - self.last_health_check >= HEALTH_POLL_SECONDS:
            result = check_health(self.config)
            self.health_state, self.active, self.port_listening = result
            self.last_health_check = current_time

        if current_time - self.last_cpu_check >= CPU_POLL_SECONDS:
            self.cpu = get_openclaw_cpu_percent(self.config) if self.active else 0.0
            self.last_cpu_check = current_time

        logs = read_new_logs(self.runtime_reader, self.journal_follower)
        state, detail = choose_state(self.health_state, classify_from_logs(logs), self.cpu)

        payload = {
            "ok": state not in ("offline", "error"),
            "state": state,
            "detail": detail,
            "updated": now_iso(),
            "service": {
                "active": bool(self.active),
                "port_listening": bool(self.port_listening),
                "cpu_percent": float(self.cpu),
            },
        }
        self.transition_logger.log_if_changed(describe_status_payload(payload))
        return payload

    def close(self):
        self.journal_follower.close()
