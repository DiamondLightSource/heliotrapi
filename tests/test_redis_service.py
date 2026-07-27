import shutil
import socket
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from heliotrapi.redis_service import build_client, ensure_running, stop


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_build_client_uses_config_fields():
    config = MagicMock()
    config.redis.host = "example.com"
    config.redis.port = 1234
    config.redis.db = 2
    config.redis.password = "hunter2"

    client = build_client(config)

    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["host"] == "example.com"
    assert kwargs["port"] == 1234
    assert kwargs["db"] == 2
    assert kwargs["password"] == "hunter2"


def test_ensure_running_skips_when_already_reachable():
    port = _free_port()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)

        config = MagicMock()
        config.redis.host = "127.0.0.1"
        config.redis.port = port

        with patch("heliotrapi.redis_service.subprocess.Popen") as mock_popen:
            result = ensure_running(config)

    assert result is None
    mock_popen.assert_not_called()


def test_ensure_running_rejects_unreachable_remote_host():
    config = MagicMock()
    config.redis.host = "some-remote-host.example.com"
    config.redis.port = _free_port()

    with pytest.raises(RuntimeError, match="not reachable"):
        ensure_running(config)


def test_ensure_running_raises_when_binary_missing(tmp_path):
    config = MagicMock()
    config.redis.host = "localhost"
    config.redis.port = _free_port()
    config.redis.data_dir = str(tmp_path)

    with patch(
        "heliotrapi.redis_service.subprocess.Popen", side_effect=FileNotFoundError
    ):
        with pytest.raises(RuntimeError, match="redis-server"):
            ensure_running(config)


def test_ensure_running_raises_if_process_exits_immediately(tmp_path):
    config = MagicMock()
    config.redis.host = "localhost"
    config.redis.port = _free_port()
    config.redis.data_dir = str(tmp_path)

    fake_process = MagicMock()
    fake_process.poll.return_value = 1
    fake_process.returncode = 1

    with patch("heliotrapi.redis_service.subprocess.Popen", return_value=fake_process):
        with pytest.raises(RuntimeError, match="exited immediately"):
            ensure_running(config)


def test_stop_terminates_process():
    process = MagicMock()
    process.wait.return_value = None

    stop(process)

    process.terminate.assert_called_once()
    process.wait.assert_called_once()


def test_stop_kills_after_timeout():
    process = MagicMock()
    process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="redis-server", timeout=5),
        None,
    ]

    stop(process)

    process.terminate.assert_called_once()
    process.kill.assert_called_once()


def test_stop_noop_for_none():
    stop(None)  # should not raise


@pytest.mark.skipif(
    shutil.which("redis-server") is None, reason="redis-server not installed"
)
def test_ensure_running_starts_real_server(tmp_path):
    config = MagicMock()
    config.redis.host = "127.0.0.1"
    config.redis.port = _free_port()
    config.redis.data_dir = str(tmp_path)

    process = ensure_running(config)
    try:
        assert process is not None
        with socket.create_connection(
            (config.redis.host, config.redis.port), timeout=1
        ):
            pass
        assert (tmp_path / "appendonlydir").exists()
    finally:
        stop(process)
