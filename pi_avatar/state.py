import json
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class StateWriter:
    def __init__(self, state_file):
        self.state_file = Path(state_file)
        self.last_written_payload = None
        self.last_written_state = None

    def write(self, state, detail=""):
        payload = {
            "state": state,
            "detail": detail,
            "updated": now_iso(),
        }

        comparable_payload = {
            "state": state,
            "detail": detail,
        }

        if self.last_written_payload == comparable_payload:
            return False

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        tmp_file.write_text(json.dumps(payload, indent=2))
        tmp_file.replace(self.state_file)

        self.last_written_payload = comparable_payload
        self.last_written_state = payload["state"]
        return True
