"""Interface for `python -m heliotrapi`."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from xrpd_toolbox.utils.messenger import Messenger

import heliotrapi
from heliotrapi._version import __version__
from heliotrapi.analysis_core import MODULE_NAMES, initialize_analyses
from heliotrapi.api.routes import ROUTER
from heliotrapi.config import Config
from heliotrapi.task_queue import QueueManager, RabbitMQListener, cleanup_results

config: Config = Config.load_config()


@asynccontextmanager
async def lifespan(app: FastAPI):

    rabbit_task = None

    if config.rabbitmq.enabled:
        messenger = Messenger(
            host=config.rabbitmq.host,
            port=config.rabbitmq.port,
            username=config.rabbitmq.username,
            password=config.rabbitmq.password,
            auto_subscribe=False,
        )
    else:
        messenger = None

    queue_manager = QueueManager(workers=config.queue.workers, messenger=messenger)

    workers = [
        asyncio.create_task(queue_manager.worker())
        for _ in range(queue_manager.workers)
    ]

    cleanup_task = asyncio.create_task(
        cleanup_results(
            queue_manager,
            ttl=config.results.ttl_seconds,
            interval=config.cleanup.interval_seconds,
        )
    )

    if config.rabbitmq.enabled:
        rabbit_listener = RabbitMQListener(
            queue_manager=queue_manager,
            host=config.rabbitmq.host,
            port=config.rabbitmq.port,
            username=config.rabbitmq.username,
            password=config.rabbitmq.password,
            destinations=config.rabbitmq.destinations,
        )

        rabbit_task = asyncio.create_task(rabbit_listener.start())

    app.state.queue_manager = queue_manager
    app.state.config = config

    logging.info("API started")

    yield

    logging.info("Shutting down")

    for task in workers:
        task.cancel()

    cleanup_task.cancel()

    if rabbit_task is not None:
        rabbit_task.cancel()


def start_api() -> FastAPI:

    logger = logging.getLogger(__name__)
    initialize_analyses(register_all=config.plugins.register_all)
    logger.info(f"{MODULE_NAMES} have been loaded")
    logger.info(f"version: {__version__}")

    app = FastAPI(
        title=heliotrapi.__name__.capitalize(),
        version=__version__,
        description="An API for fast data analysis jobs",
        lifespan=lifespan,
    )

    # Include API routes
    app.include_router(ROUTER)

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Serve index.html for the root path
    @app.get("/")
    async def serve_index():
        index_file = Path(__file__).parent / "templates" / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "HeliotrAPI Analysis. Visit /docs for API documentation"}

    return app
