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

    def fake_uvicorn_run(app, factory, host, port, reload, workers):
        assert host == "127.0.0.1"
        assert port == 8000
        assert reload is True
        assert workers == 2

    monkeypatch.setattr("heliotrapi.__main__.uvicorn.run", fake_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(config_file), "--host", "127.0.0.1", "serve"],
    )

    assert result.exit_code == 0
