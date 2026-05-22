"""Interface for ``python -m heliotrapi``."""

import logging
from pathlib import Path

import click
import uvicorn
from heliotrapi.config import Config
from heliotrapi.server import start_api

from ._version import __version__

__all__ = ["main"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
@click.pass_context
def main(
    ctx: click.Context,
    config: Path | None,
    host: str | None,
) -> None:
    try:
        loaded_config = Config.load_config(config)
    except FileNotFoundError as fnfe:
        raise FileNotFoundError(f"Config file not found: {fnfe.filename}") from fnfe

    if host:
        loaded_config.server.host = host

    ctx.ensure_object(dict)
    ctx.obj["config"] = loaded_config

    if ctx.invoked_subcommand is None:
        print("Please invoke subcommand!")


@main.command(name="serve")
@click.pass_context
def serve(ctx: click.Context):
    config = ctx.obj["config"]

    logger.info(f"host: {config.server.host}")
    logger.info(f"port {config.server.port}")

    uvicorn.run(
        f"heliotrapi.server:{start_api.__name__}",
        factory=True,
        host=config.server.host,
        port=int(config.server.port),
        reload=True,
        workers=config.queue.workers,
    )


if __name__ == "__main__":
    main()
