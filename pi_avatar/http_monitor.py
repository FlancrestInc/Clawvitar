import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import error, request

from .constants import FAST_POLL_SECONDS, VALID_STATES
from .state import StateWriter


@dataclass(frozen=True)
class PollResult:
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

    def log_if_changed(self, result):
        key = (result.health, result.state, result.message)
        if key == self.last_key:
            return False

        self.log_func(result.message)
        self.last_key = key
        return True


def fetch_status(config):
    try:
        with request.urlopen(config.status_url, timeout=config.http_timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except (OSError, error.URLError) as exc:
        return None, f"Status feed unavailable: {exc}"

    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON from status feed: {exc}"


def _parse_timestamp(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def status_to_state(payload, now=None, stale_seconds=15):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    state = payload.get("state")
    detail = payload.get("detail", "")

    if state not in VALID_STATES:
        return "offline", f"Unknown remote avatar state: {state}"

    updated = _parse_timestamp(payload.get("updated"))
    if updated is None:
        return "offline", "Remote status timestamp missing or invalid"

    age = (now - updated).total_seconds()
    if age > stale_seconds:
        return "offline", "Remote status feed is stale"

    return state, detail


def describe_poll_result(config, payload, error_message):
    if payload is None:
        return PollResult(
            health="offline",
            state="offline",
            message=f"offline: {error_message or 'Status feed unavailable'} ({config.status_url})",
        )

    state, detail = status_to_state(
        payload,
        now=datetime.now(timezone.utc),
        stale_seconds=config.stale_status_seconds,
    )
    health = "connected" if state != "offline" else "offline"
    detail_suffix = f": {detail}" if detail else ""

    return PollResult(
        health=health,
        state=state,
        message=f"{health}: {config.status_url} -> {state}{detail_suffix}",
    )


def poll_once(config, writer=None, transition_logger=None):
    writer = writer or StateWriter(config.state_file)
    payload, error_message = fetch_status(config)
    result = describe_poll_result(config, payload, error_message)

    if transition_logger:
        transition_logger.log_if_changed(result)

    if payload is None:
        return writer.write("offline", error_message or "Status feed unavailable")

    state, detail = status_to_state(
        payload,
        now=datetime.now(timezone.utc),
        stale_seconds=config.stale_status_seconds,
    )
    return writer.write(state, detail)


def run_monitor(config):
    writer = StateWriter(config.state_file)
    transition_logger = TransitionLogger()
    writer.write("booting", "Avatar monitor starting")
    print(f"monitor starting: polling {config.status_url}", flush=True)

    while True:
        poll_once(config, writer, transition_logger)
        time.sleep(FAST_POLL_SECONDS)
