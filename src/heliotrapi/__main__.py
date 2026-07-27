"""Interface for ``python -m heliotrapi``."""

from pathlib import Path

import click
import numpy as np

from heliotrapi import redis_service
from heliotrapi.analyses.peak_fitting import gaussian
from heliotrapi.client import AnalysisClient
from heliotrapi.config import Config

# from heliotrapi.logging import logger
from ._version import __version__

__all__ = ["main"]


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, message="%(version)s")
@click.option(
    "--config",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to config file",
)
@click.option(
    "--host",
    type=str,
    default=None,
    help="Host override",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="port override",
)
@click.pass_context
def main(
    ctx: click.Context,
    host: str | None,
    port: int | None,
    config: Path | None,
) -> None:

    try:
        loaded_config = Config.load_config(config)
    except FileNotFoundError as fnfe:
        raise FileNotFoundError(f"Config file not found: {fnfe.filename}") from fnfe

    if host:
        loaded_config.server.host = host

    if port:
        loaded_config.server.port = port

    ctx.ensure_object(dict)
    ctx.obj["config"] = loaded_config

    if ctx.invoked_subcommand is None:
        print("Please invoke subcommand!")


def _run_uvicorn(config: Config) -> None:
    """Single OS process, run in this one - the dev/local default."""
    import uvicorn

    from heliotrapi.server import start_api

    uvicorn.run(
        start_api(),
        factory=False,
        host=config.server.host,
        port=int(config.server.port),
        reload=False,
    )


def _run_gunicorn(config: Config) -> None:
    """Multiple OS worker processes: launch Gunicorn in-process (this CLI
    process becomes the Gunicorn arbiter) with --preload, so plugin and
    analysis loading (which can do git clone/uv pip install) happens once
    before forking workers, not once per worker."""
    from gunicorn.app.base import BaseApplication
    from gunicorn.util import import_app

    class _GunicornApp(BaseApplication):
        def __init__(self, app_uri: str, options: dict):
            self.app_uri = app_uri
            self.options = options
            super().__init__()

        def load_config(self):
            for key, value in self.options.items():
                self.cfg.set(key, value)

        def load(self):
            return import_app(self.app_uri)

    _GunicornApp(
        "heliotrapi.asgi:app",
        {
            "bind": f"{config.server.host}:{int(config.server.port)}",
            "workers": int(config.uvicorn.workers),
            "worker_class": "uvicorn.workers.UvicornWorker",
            "preload_app": True,
        },
    ).run()


@main.command(name="serve")
@click.pass_context
def serve(ctx: click.Context):

    config = ctx.obj["config"]

    # Starts a local redis-server if config.redis isn't already reachable,
    # so `heliotrapi serve` is self-contained rather than requiring Redis to
    # be booted separately. Must happen once here, before Gunicorn forks any
    # workers, so they all connect to the same instance.
    redis_process = redis_service.ensure_running(config)

    try:
        if int(config.uvicorn.workers) <= 1:
            _run_uvicorn(config)
        else:
            _run_gunicorn(config)
    finally:
        redis_service.stop(redis_process)


@main.command(name="run_client_test")
@click.pass_context
def run_client_test(ctx: click.Context):

    x = np.round(np.linspace(0, 20, 50), 3)
    y = np.round(gaussian(x, 10, 5, 1) + (np.random.rand(x.shape[-1]) / 5), 3)

    config = ctx.obj["config"]

    url = f"http://{config.server.host}:{config.server.port}"

    client = AnalysisClient(url)

    for i in range(5):
        id = client.submit("double", number=i)
        _ = client.get_request_id_result(id)
    client.submit("gaussian_fit", x=x, y=y)

    for i in client.get_all_results():
        print(i, "\n")

    available_analyses = client.available_analyses(as_strings=True)

    for analysis in available_analyses:
        print(analysis)

    # client.submit("gaussian_fit", num=x, g=y)
    # print(client.get_result())


if __name__ == "__main__":
    main()
