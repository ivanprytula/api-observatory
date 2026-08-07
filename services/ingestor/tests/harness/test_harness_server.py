"""Deterministic local HTTP boundaries for composed optional-flow tests."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Handler(BaseHTTPRequestHandler):
    """Serve fixed source, provider, and AI responses without credentials."""

    retry_attempts = 0

    def do_GET(self) -> None:  # noqa: N802
        payloads = {
            "/health": {"status": "ok"},
            "/source/baseline": {
                "status": "ok",
                "payload": {"temperature": 20.5, "region": "eu"},
            },
            "/source/breaking": {
                "status": {"code": "ok"},
                "payload": {"region": "eu"},
            },
        }
        payload = payloads.get(self.path)
        if payload is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._json(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/provider/retry":
            type(self).retry_attempts += 1
            status = (
                HTTPStatus.SERVICE_UNAVAILABLE
                if self.retry_attempts == 1
                else HTTPStatus.ACCEPTED
            )
            self._json(status, {"attempt": self.retry_attempts})
            return
        if self.path == "/provider/permanent":
            self._json(HTTPStatus.BAD_REQUEST, {"error": "permanent"})
            return
        if self.path == "/ai/review":
            self._json(
                HTTPStatus.OK,
                {
                    "severity": "critical",
                    "reasoning": "Deterministic breaking-contract review.",
                    "recommended_action": "Roll back the incompatible response.",
                },
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
