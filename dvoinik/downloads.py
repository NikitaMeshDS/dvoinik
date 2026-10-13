"""Выдача подготовленных файлов: одноразовая ссылка привязана к действующей сессии."""

from __future__ import annotations

import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auth import AuthError


def create_download_server(auth, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # URL содержит секрет краткоживущей ссылки; не пишем его в access log.
            pass

        def do_GET(self):
            self._download()

        def do_HEAD(self):
            self._download(head=True)

        def do_POST(self):
            self._response(405, b"Method not allowed", "text/plain")

        def _download(self, head=False):
            match = re.fullmatch(r"/download/([A-Za-z0-9_-]{43})", self.path)
            if not match:
                self._response(404, b"Not found", "text/plain", head=head)
                return
            try:
                body, mime, filename = auth.consume_export(match[1], head=head)
            except AuthError:
                self._response(
                    410,
                    "Ссылка недоступна. Обновите страницу Двойника и скачайте файл заново.".encode(),
                    "text/plain; charset=utf-8",
                    head=head,
                )
            else:
                self._response(200, body, mime, filename, head=head)

        def _response(self, status, body, mime, filename=None, head=False):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            if not head:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
