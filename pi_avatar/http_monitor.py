import json
import time
from datetime import datetime, timezone
from urllib import error, request

from .constants import FAST_POLL_SECONDS, VALID_STATES
from .state import StateWriter


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


def poll_once(config, writer=None):
    writer = writer or StateWriter(config.state_file)
    payload, error_message = fetch_status(config)

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
    writer.write("booting", "Avatar monitor starting")

    while True:
        poll_once(config, writer)
        time.sleep(FAST_POLL_SECONDS)
