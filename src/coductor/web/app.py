"""Framework-free local console API app."""

from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pydantic import BaseModel

from coductor.web.control_service import ConsoleControlError, ConsoleControlService
from coductor.web.doctor_service import ConsoleDoctorService
from coductor.web.read_service import ConsoleReadError, ConsoleReadService
from coductor.web.schemas import ConsoleError, ConsoleResponse


@dataclass(frozen=True)
class LocalConsoleResponse:
    status: int
    body: dict[str, object] | str
    content_type: str = "application/json; charset=utf-8"

    @property
    def text(self) -> str:
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body, ensure_ascii=False)

    @property
    def bytes(self) -> bytes:
        return self.text.encode("utf-8")


class LocalConsoleApp:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.control_service = ConsoleControlService(root)
        self.doctor_service = ConsoleDoctorService(root)
        self.read_service = ConsoleReadService(root)
        self.static_root = Path(__file__).parent / "static"

    def handle(self, method: str, raw_path: str) -> LocalConsoleResponse:
        parsed = urlparse(raw_path)
        path = unquote(parsed.path)
        try:
            if method == "GET":
                return self._handle_get(path)
            if method == "POST":
                return self._handle_post(path)
            return _error("method not allowed", status=HTTPStatus.METHOD_NOT_ALLOWED)
        except ConsoleReadError as error:
            return _error(
                error.message,
                status=HTTPStatus.BAD_REQUEST,
                recoverable=error.recoverable,
                next_command=error.next_command,
            )
        except ConsoleControlError as error:
            return _error(
                error.message,
                status=HTTPStatus(error.status_code),
                recoverable=error.recoverable,
                next_command=error.next_command,
            )

    def _handle_get(self, path: str) -> LocalConsoleResponse:
        if path == "/":
            return self._static_file("index.html", content_type="text/html; charset=utf-8")
        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            return self._static_file(relative, content_type=_content_type(relative))
        if path == "/api/health":
            return _ok(self.read_service.health())
        if path == "/api/runs":
            return _ok(self.read_service.list_runs())
        if path.startswith("/api/runs/"):
            return self._handle_run_get(path)
        if path == "/api/doctor":
            return _ok(self.doctor_service.report())
        return _error("not found", status=HTTPStatus.NOT_FOUND)

    def _handle_run_get(self, path: str) -> LocalConsoleResponse:
        remainder = path.removeprefix("/api/runs/")
        parts = remainder.split("/", 2)
        run_id = parts[0]
        if len(parts) == 1:
            return _ok(self.read_service.get_run(run_id))
        section = parts[1]
        rest = parts[2] if len(parts) > 2 else ""
        if section == "events":
            return _ok(self.read_service.get_events(run_id))
        if section == "artifacts":
            if rest:
                return _ok(self.read_service.get_artifact(run_id, rest))
            return _ok(self.read_service.list_artifacts(run_id))
        if section == "report":
            return _ok({"raw_text": self.read_service.get_report(run_id)})
        if section == "logs":
            return _ok(self.read_service.get_log(run_id, rest))
        return _error("not found", status=HTTPStatus.NOT_FOUND)

    def _handle_post(self, path: str) -> LocalConsoleResponse:
        if not path.startswith("/api/runs/"):
            return _error("not found", status=HTTPStatus.NOT_FOUND)
        remainder = path.removeprefix("/api/runs/")
        parts = remainder.split("/")
        if len(parts) == 3 and parts[1] == "actions":
            run_id = parts[0]
            action = parts[2]
            return _ok(self.control_service.run_action(run_id, action))
        return _error("not found", status=HTTPStatus.NOT_FOUND)

    def _static_file(self, relative_path: str, *, content_type: str) -> LocalConsoleResponse:
        if "/" in relative_path or "\\" in relative_path or relative_path.startswith("."):
            return _error("static asset not found", status=HTTPStatus.NOT_FOUND)
        path = self.static_root / relative_path
        if not path.exists() or not path.is_file():
            return _error("static asset not found", status=HTTPStatus.NOT_FOUND)
        return LocalConsoleResponse(
            status=HTTPStatus.OK,
            body=path.read_text(encoding="utf-8"),
            content_type=content_type,
        )


def create_app(root: Path) -> LocalConsoleApp:
    return LocalConsoleApp(root)


def _ok(data: object) -> LocalConsoleResponse:
    payload: Any
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    elif isinstance(data, list):
        payload = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in data
        ]
    else:
        payload = data
    response = ConsoleResponse[object](ok=True, data=payload, error=None)
    return LocalConsoleResponse(status=HTTPStatus.OK, body=response.model_dump(mode="json"))


def _error(
    message: str,
    *,
    status: HTTPStatus,
    recoverable: bool = True,
    next_command: str | None = None,
) -> LocalConsoleResponse:
    response = ConsoleResponse[object](
        ok=False,
        data=None,
        error=ConsoleError(
            message=message,
            recoverable=recoverable,
            next_command=next_command,
        ),
    )
    return LocalConsoleResponse(status=status, body=response.model_dump(mode="json"))


def _content_type(path: str) -> str:
    if path.endswith(".css"):
        return "text/css; charset=utf-8"
    if path.endswith(".js"):
        return "application/javascript; charset=utf-8"
    return "text/plain; charset=utf-8"
