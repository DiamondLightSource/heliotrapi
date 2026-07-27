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


def test_cli_serve_invokes_uvicorn():
    cmd = [sys.executable, "-m", "heliotrapi", "serve"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    output = (stdout + stderr).decode()
    assert "Started server process" in output


def test_cli_serve_multi_worker_launches_gunicorn():
    from gunicorn.app.base import BaseApplication

    # serve() reads ctx.obj["config"], but that's set by the `main` group's
    # own callback (via Config.load_config()) before any subcommand runs -
    # passing obj={...} to runner.invoke() would just get overwritten, so
    # the config must be mocked at its source instead.
    config_mock = MagicMock()
    config_mock.server.host = "localhost"
    config_mock.server.port = 8000
    config_mock.uvicorn.workers = 3

    captured = {}

    def fake_run(self):
        captured["app_uri"] = self.app_uri
        captured["options"] = self.options

    runner = CliRunner()
    with (
        patch("heliotrapi.__main__.Config.load_config", return_value=config_mock),
        patch("heliotrapi.redis_service.ensure_running", return_value=None),
        patch.object(BaseApplication, "run", fake_run),
    ):
        result = runner.invoke(
            main,
            ["serve"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0
    assert captured["app_uri"] == "heliotrapi.asgi:app"
    assert captured["options"] == {
        "bind": "localhost:8000",
        "workers": 3,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "preload_app": True,
    }


def test_serve_raises_exception_when_dependencies_missing():
    runner = CliRunner()

    config_mock = MagicMock()
    config_mock.server.host = "localhost"
    config_mock.server.port = "8000"
    config_mock.uvicorn.workers = 1

    with (
        pytest.raises(ImportError),
        patch("heliotrapi.redis_service.ensure_running", return_value=None),
    ):
        with patch.dict("sys.modules", {"uvicorn": None, "heliotrapi.server": None}):
            result = runner.invoke(
                main,
                ["serve"],
                obj={"config": config_mock},
                catch_exceptions=False,
            )

        assert result.exit_code != 0
        assert isinstance(result.exception, ImportError)
        assert "pip install heliotrapi" in str(result.exception)


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
