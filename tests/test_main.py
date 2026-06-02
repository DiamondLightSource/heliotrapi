import logging
from typing import cast

from click.testing import CliRunner

from heliotrapi.__main__ import main


def test_main_no_subcommand_prints_message():
    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    assert "Please invoke subcommand!" in result.output


def test_main_config_not_found():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", "missing.yaml"])

    assert result.exit_code == 0
    assert "Please invoke subcommand!" in result.output


def test_main_host_override(monkeypatch, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("server:\n  host: 0.0.0.0\n  port: 8000\n")

    def fake_uvicorn_run(app, factory, host, port, reload):
        assert host == "127.0.0.1"
        assert port == 8000

    monkeypatch.setattr("heliotrapi.__main__.uvicorn.run", fake_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(config_file), "--host", "127.0.0.1", "serve"],
    )

    assert result.exit_code == 0


def test_ignore_healthz_access_logs():
    from heliotrapi.server import HealthzAccessLogFilter, configure_access_log_filter

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.filters.clear()

    configure_access_log_filter()

    filter_obj = cast(HealthzAccessLogFilter, access_logger.filters[-1])
    assert isinstance(filter_obj, HealthzAccessLogFilter)
    assert (
        filter_obj.filter(
            logging.LogRecord(
                name="uvicorn.access",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg='127.0.0.1 - - [02/Jun/2026:00:00:00 +0000] "GET /healthz HTTP/1.1" 200',  # noqa
                args=(),
                exc_info=None,
            )
        )
        is False
    )
    assert (
        filter_obj.filter(
            logging.LogRecord(
                name="uvicorn.access",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg='127.0.0.1 - - [02/Jun/2026:00:00:00 +0000] "GET /api HTTP/1.1" 200',  # noqa
                args=(),
                exc_info=None,
            )
        )
        is True
    )
