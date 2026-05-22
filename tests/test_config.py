from indigoapi.config import Config, RabbitMQConfig


def test_config_loads_path_from_env(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("server:\n  host: 127.0.0.1\n  port: 1234\n")
    monkeypatch.setenv("CONFIG_PATH", str(config_file))

    cfg = Config.load_config()

    assert cfg.server.host == "127.0.0.1"
    assert cfg.server.port == 1234


def test_config_returns_default_for_missing_file(tmp_path):
    cfg = Config.load_config(tmp_path / "nope.yaml")

    assert cfg.server.host == "0.0.0.0"
    assert cfg.queue.workers == 2


def test_config_default_values():
    cfg = Config()
    assert cfg.results.ttl_seconds == 3600
    assert cfg.cleanup.interval_seconds == 300


def test_rabbitmq_address_property():
    cfg = RabbitMQConfig(
        host="example.com", username="alice", password="secret", port=1234
    )
    assert cfg.address == "stomp://alice:secret@example.com:1234/"
