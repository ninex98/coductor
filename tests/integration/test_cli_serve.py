from __future__ import annotations

from typer.testing import CliRunner

from coductor.cli import app
from coductor.web import server as web_server
from coductor.web.server import ServeOptionsError, create_http_server, validate_serve_options


def test_cli_help_lists_serve_command() -> None:
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.output
    assert "本地 Web 控制台" in result.output


def test_serve_options_reject_non_loopback_without_lan_opt_in() -> None:
    try:
        validate_serve_options(host="0.0.0.0", allow_lan=False)
    except ServeOptionsError as error:
        assert "requires --allow-lan" in str(error)
    else:  # pragma: no cover - failure path
        raise AssertionError("non-loopback host should require --allow-lan")


def test_serve_options_accept_loopback_defaults() -> None:
    validate_serve_options(host="127.0.0.1", allow_lan=False)
    validate_serve_options(host="localhost", allow_lan=False)


def test_create_http_server_binds_loopback_without_optional_dependencies(tmp_path) -> None:
    server = create_http_server(
        tmp_path,
        host="127.0.0.1",
        port=8765,
        bind_and_activate=False,
    )
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] == 8765
    finally:
        server.server_close()


def test_cli_serve_reports_bind_failure_without_traceback(monkeypatch) -> None:
    def fail_bind(*args, **kwargs) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(web_server, "create_http_server", fail_bind)
    cli_runner = CliRunner()

    result = cli_runner.invoke(app, ["serve", "--port", "8765"])

    assert result.exit_code == 1
    assert "failed to bind local console" in result.output
    assert "Traceback" not in result.output
