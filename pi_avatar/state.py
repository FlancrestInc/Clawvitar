import json
import time
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class StateWriter:
    def __init__(self, state_file, unchanged_write_seconds=5):
        self.state_file = Path(state_file)
        self.unchanged_write_seconds = unchanged_write_seconds
        self.last_written_payload = None
        self.last_written_state = None
        self.last_write_time = 0

    def write(self, state, detail=""):
        current_time = time.time()
        payload = {
            "state": state,
            "detail": detail,
            "updated": now_iso(),
        }

        comparable_payload = {
            "state": state,
            "detail": detail,
        }

        if (
            self.last_written_payload == comparable_payload
            and current_time - self.last_write_time < self.unchanged_write_seconds
        ):
            return False

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        tmp_file.write_text(json.dumps(payload, indent=2))
        tmp_file.replace(self.state_file)

        self.last_written_payload = comparable_payload
        self.last_written_state = payload["state"]
        self.last_write_time = current_time
        return True
