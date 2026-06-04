import subprocess
import sys
from unittest.mock import MagicMock, patch

import click
import numpy as np
import pytest
from click.testing import CliRunner

from heliotrapi import __version__
from heliotrapi.__main__ import main, run_client_test


@pytest.fixture
def click_ctx():
    ctx = click.Context(run_client_test)
    ctx.obj = {
        "config": MagicMock(
            server=MagicMock(
                host="localhost",
                port=8000,
            )
        )
    }
    return ctx


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

    monkeypatch.setattr("uvicorn.run", fake_run)

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


def test_run_client_test():
    runner = CliRunner()

    mock_client = MagicMock()
    mock_client.submit.return_value = "fake-id"
    mock_client.get_request_id_result.return_value = {"status": "ok"}
    mock_client.get_all_results.return_value = [{"a": 1}]
    mock_client.available_analyses.return_value = ["double", "gaussian_fit"]

    fake_config = MagicMock()
    fake_config.server.host = "localhost"
    fake_config.server.port = 8000

    with (
        patch("heliotrapi.__main__.Config.load_config", return_value=fake_config),
        patch("heliotrapi.__main__.AnalysisClient", return_value=mock_client),
        patch("heliotrapi.__main__.gaussian", return_value=np.ones(50)),
        patch("numpy.random.rand", return_value=np.zeros(50)),
    ):
        result = runner.invoke(
            main,
            [
                "--config",
                "dummy.yml",
                "--host",
                "localhost",
                "--port",
                "8000",
                "run_client_test",
            ],
        )

    assert result.exit_code == 0

    # 5 loop submissions + 1 gaussian_fit
    assert mock_client.submit.call_count == 6

    mock_client.submit.assert_any_call("double", number=0)
    mock_client.submit.assert_any_call("double", number=4)

    mock_client.available_analyses.assert_called_once()
    mock_client.get_all_results.assert_called_once()
