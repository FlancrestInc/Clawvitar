#!/usr/bin/env python3

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pi_avatar.config import load_config
from pi_avatar.openclaw_status import StatusSampler


def make_handler(sampler):
    class StatusHandler(BaseHTTPRequestHandler):
        def _write_json(self, status, payload):
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                self._write_json(200, {"ok": True})
                return

            if self.path != "/status":
                self._write_json(404, {"ok": False, "error": "not found"})
                return

            self._write_json(200, sampler.sample())

        def log_message(self, format, *args):
            return

    return StatusHandler


def main():
    config = load_config(os.environ)
    sampler = StatusSampler(config)
    server = ThreadingHTTPServer(
        (config.status_bind_host, config.status_bind_port),
        make_handler(sampler),
    )

    try:
        server.serve_forever()
    finally:
        sampler.close()
        server.server_close()


if __name__ == "__main__":
    main()
