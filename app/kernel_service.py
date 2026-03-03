"""Minimal HTTP kernel service for gateway integration in local development."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict
from uuid import uuid4


@dataclass
class KernelServiceConfig:
    host: str = "127.0.0.1"
    port: int = 8000


class KernelRequestHandler(BaseHTTPRequestHandler):
    server_version = "RAGGPTKernel/0.1"

    def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "python-kernel",
                },
            )
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/qa":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": {
                        "code": "KERNEL_INVALID_REQUEST",
                        "message": "Request body must be valid JSON",
                        "retryable": False,
                    }
                },
            )
            return

        query = str(payload.get("query", "")).strip()
        mode = str(payload.get("mode", "local")).lower()
        if not query:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": {
                        "code": "KERNEL_INVALID_REQUEST",
                        "message": "Field `query` is required",
                        "retryable": False,
                    }
                },
            )
            return

        trace_id = str(payload.get("traceId") or uuid4())
        response = {
            "traceId": trace_id,
            "answer": f"[mock-{mode}] Received query: {query}",
            "sources": [
                {
                    "source_type": "local",
                    "source_id": "mock-source-1",
                    "title": "Mock local evidence",
                    "snippet": "Replace this response by integrating app.qa in task 4.1.",
                    "locator": "chunk:mock-1",
                    "score": 0.42,
                }
            ],
        }
        self._write_json(HTTPStatus.OK, response)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local kernel mock service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    config = KernelServiceConfig(host=args.host, port=args.port)
    server = HTTPServer((config.host, config.port), KernelRequestHandler)
    print(f"python-kernel service listening on http://{config.host}:{config.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
