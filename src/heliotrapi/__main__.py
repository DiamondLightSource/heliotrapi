"""Interface for ``python -m heliotrapi``."""

from pathlib import Path

import click
import numpy as np

from heliotrapi import logger
from heliotrapi.analyses.peak_fitting import gaussian
from heliotrapi.client import AnalysisClient
from heliotrapi.config import Config

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


@main.command(name="serve")
@click.pass_context
def serve(ctx: click.Context):

    import uvicorn

    from heliotrapi.server import start_api

    # try:
    #     import uvicorn

    #     from heliotrapi.server import start_api
    # except Exception as e:
    #     raise Exception(
    #         "You must have install all dependencies - pip install heliotrapi"
    #     ) from e

    config = ctx.obj["config"]

    logger.info(f"host: {config.server.host}")
    logger.info(f"port {config.server.port}")

    uvicorn.run(
        f"heliotrapi.server:{start_api.__name__}",
        factory=True,
        host=config.server.host,
        port=int(config.server.port),
        reload=False,
    )


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
