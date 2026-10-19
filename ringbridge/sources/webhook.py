"""HTTP webhook: anything that can send an HTTP request can trigger an alert.

    curl -X POST http://127.0.0.1:8787/alert \\
         -H "Authorization: Bearer <token>" \\
         -d '{"sender": "CI", "text": "deploy failed"}'

GET /health returns 200, handy for uptime checks.
"""

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ringbridge.events import Event
from ringbridge.sources.base import Source, register

MAX_BODY = 64 * 1024


@register
class WebhookSource(Source):
    type = "webhook"

    def check(self):
        problems = []
        token = self.cfg.get("token", "")
        if len(token) < 16 or token.startswith("change-me"):
            problems.append(f"source '{self.name}': set a random `token` of at least 16 characters")
        return problems

    def address(self):
        host, _, port = self.cfg.get("listen", "127.0.0.1:8787").rpartition(":")
        return host or "127.0.0.1", int(port)

    def start(self):
        source = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                source.log.debug(fmt, *args)

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if urlparse(self.path).path == "/health":
                    self.reply(200, {"status": "ok"})
                else:
                    self.reply(404, {"error": "not found"})

            def do_POST(self):
                url = urlparse(self.path)
                if url.path != source.cfg.get("path", "/alert"):
                    return self.reply(404, {"error": "not found"})
                given = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                given = given or parse_qs(url.query).get("token", [""])[0]
                if not hmac.compare_digest(given.encode(), source.cfg["token"].encode()):
                    source.log.warning("Rejected request from %s: bad token", self.client_address[0])
                    return self.reply(401, {"error": "unauthorized"})
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self.reply(413, {"error": "body too large"})
                raw = self.rfile.read(length) if length else b""
                try:
                    data = json.loads(raw) if raw.strip() else {}
                    if not isinstance(data, dict):
                        raise ValueError
                except ValueError:
                    data = {"text": raw.decode(errors="replace")}
                source.submit(Event(source=source.label,
                                    sender=str(data.get("sender") or data.get("title") or ""),
                                    text=str(data.get("text") or "")))
                self.reply(202, {"status": "accepted"})

        self.server = ThreadingHTTPServer(self.address(), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.log.info("Webhook listening on http://%s:%d%s", *self.address(), self.cfg.get("path", "/alert"))

    def stop(self):
        if getattr(self, "server", None):
            self.server.shutdown()
