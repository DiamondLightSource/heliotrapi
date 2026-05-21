"""Interface for `python -m indigoapi`."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from xrpd_toolbox.utils.messenger import Messenger

from indigoapi.analyses import MODULE_NAMES, initialize_analyses
from indigoapi.api.routes import ROUTER
from indigoapi.cleanup import cleanup_results
from indigoapi.config import Config
from indigoapi.queue_manager import QueueManager
from indigoapi.rabbitmq_listener import RabbitMQListener

from . import __version__

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
        title="IndigoAPI",
        version=__version__,
        description="An API for fast data analysis jobs",
        lifespan=lifespan,
    )

    app.include_router(ROUTER)

    return app
