"""Everything about how heliotrapi gets a working Redis connection.

Redis holds the state - the job queue, results, and the RabbitMQ listener
lock - that must be shared across multiple Gunicorn worker processes, since
plain process memory can't be. This module is the single place responsible
for that: building the async client the rest of the app uses (build_client),
and - so `heliotrapi serve` is self-contained rather than requiring Redis to
be booted separately - starting a local redis-server if config.redis isn't
already reachable (ensure_running/stop).

ensure_running/stop are only ever called from the CLI entrypoint
(__main__.py). Tests build the app via start_api()/TestClient with
build_client() itself faked out (see tests/conftest.py's fake_redis_client),
and must never spawn a real OS process.
"""

import socket
import subprocess
import time
from pathlib import Path

import redis.asyncio as redis_asyncio

from heliotrapi.config import Config
from heliotrapi.logger import logger

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_STARTUP_TIMEOUT_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.1


def build_client(config: Config) -> redis_asyncio.Redis:
    """Build the client the rest of the app talks to Redis through.

    Must be called from inside `server.py`'s `lifespan()` (which runs after
    Gunicorn forks each worker process - see __main__.py) rather than at
    module import time: Redis connections must not cross a fork boundary.
    """
    return redis_asyncio.Redis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        password=config.redis.password,
        decode_responses=True,
    )


def _is_reachable(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_running(config: Config) -> subprocess.Popen | None:
    """Make sure config.redis's host:port is reachable, starting a local
    redis-server if it isn't.

    Returns the spawned process (the caller must terminate it on shutdown
    via `stop()`), or None if nothing needed to be started - either an
    existing Redis was already reachable, or config.redis points elsewhere.
    """
    host, port = config.redis.host, config.redis.port

    if _is_reachable(host, port):
        logger.info(f"Redis already reachable at {host}:{port}")
        return None

    if host not in _LOCAL_HOSTS:
        raise RuntimeError(
            f"Redis is not reachable at {host}:{port}, and that isn't a "
            "local address heliotrapi can start a server on. Start Redis "
            "yourself, or point config.redis at a reachable instance."
        )

    data_dir = Path(config.redis.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"No Redis found at {host}:{port}; starting one at '{data_dir}'")
    try:
        process = subprocess.Popen(
            [
                "redis-server",
                "--bind",
                host,
                "--port",
                str(port),
                "--dir",
                str(data_dir),
                # append-only-file persistence, fsynced every second, so
                # queue/result state survives a restart of this process.
                "--appendonly",
                "yes",
                "--appendfsync",
                "everysec",
                "--daemonize",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Detach from our controlling terminal's process group: Ctrl+C
            # sends SIGINT to the whole foreground group, and redis-server
            # would otherwise shut itself down immediately on that signal -
            # racing our own lifespan shutdown, which still needs a working
            # connection to release the RabbitMQ lock. We stop it ourselves
            # via stop() once that's done instead.
            start_new_session=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "No Redis is reachable and the 'redis-server' binary isn't "
            "installed. Install it (e.g. `apt-get install redis-server`) "
            "or point config.redis at a reachable instance."
        ) from e

    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _is_reachable(host, port):
            logger.info(f"Started embedded redis-server (pid {process.pid})")
            return process
        if process.poll() is not None:
            raise RuntimeError(
                f"redis-server exited immediately with code {process.returncode}"
            )
        time.sleep(_POLL_INTERVAL_SECONDS)

    process.terminate()
    raise RuntimeError(
        f"redis-server did not become ready within "
        f"{_STARTUP_TIMEOUT_SECONDS}s on {host}:{port}"
    )


def stop(process: subprocess.Popen | None) -> None:
    """Terminate a process started by `ensure_running()`. A no-op if it
    returned None (nothing was started)."""
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
