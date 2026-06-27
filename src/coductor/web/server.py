"""Local web console server startup helpers."""

from __future__ import annotations

import ipaddress
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from coductor.constants import VERSION
from coductor.web.app import LocalConsoleApp, create_app


class ServeOptionsError(ValueError):
    """Raised when local console serve options are unsafe."""


def validate_serve_options(*, host: str, allow_lan: bool) -> None:
    if _is_loopback_host(host):
        return
    if allow_lan:
        return
    raise ServeOptionsError(
        f"serving on {host} requires --allow-lan; default local console is loopback-only"
    )


def serve_console(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    allow_lan: bool = False,
) -> None:
    validate_serve_options(host=host, allow_lan=allow_lan)
    url = f"http://{host}:{port}"
    print(f"Coductor local console {VERSION}")
    print(f"Project root: {root}")
    print(f"URL: {url}")
    print("安全提示: 默认仅建议监听 127.0.0.1；远程 Git/PR/Secrets 能力不会由 Web 控制台默认开启。")
    if open_browser:
        webbrowser.open(url)
    try:
        server = create_http_server(root, host=host, port=port)
    except OSError as error:
        raise ServeOptionsError(
            f"failed to bind local console on {host}:{port}: {error}"
        ) from error
    server.serve_forever()


def create_http_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    bind_and_activate: bool = True,
) -> ThreadingHTTPServer:
    app = create_app(root)

    class Handler(LocalConsoleRequestHandler):
        console_app = app

    return ThreadingHTTPServer((host, port), Handler, bind_and_activate=bind_and_activate)


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalConsoleRequestHandler(BaseHTTPRequestHandler):
    console_app: LocalConsoleApp

    def do_GET(self) -> None:  # noqa: N802
        response = self.console_app.handle("GET", self.path)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response.bytes)

    def do_POST(self) -> None:  # noqa: N802
        response = self.console_app.handle("POST", self.path)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response.bytes)

    def log_message(self, format: str, *args: Any) -> None:
        return
