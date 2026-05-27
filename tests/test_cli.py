import subprocess
import sys

from click.testing import CliRunner

from heliotrapi import __version__
from heliotrapi.__main__ import main


def test_cli_version():
    cmd = [sys.executable, "-m", "heliotrapi", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__


def test_cli_help():
    cmd = [sys.executable, "-m", "heliotrapi", "--help"]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
    assert "serve" in output


def test_cli_main_no_command_prints_message():
    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert "Please invoke subcommand!" in result.output


def test_cli_serve_invokes_uvicorn(monkeypatch):
    runner = CliRunner()
    called = {}

    def fake_run(app, host=None, port=None, factory=None, reload=None, workers=None):
        called["host"] = host
        called["port"] = port
        called["app"] = app

    monkeypatch.setattr("heliotrapi.__main__.uvicorn.run", fake_run)

    class FakeConfig:
        class server:  # noqa
            host = "127.0.0.1"
            port = 8000

        class queue:  # noqa
            workers = 1

    monkeypatch.setattr(
        "heliotrapi.__main__.Config.load_config",
        lambda _: FakeConfig(),
    )

    result = runner.invoke(main, ["serve"])

    assert result.exit_code == 0
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8000
