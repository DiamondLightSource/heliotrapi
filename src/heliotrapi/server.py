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
from heliotrapi import logger
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

    queue_manager = QueueManager(
        workers=config.queue.workers,
        messenger=messenger,
        slack_webhook_url=config.alerts.slack_webhook_url
        if config.alerts.slack_webhook_url != ""
        else None,
    )

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


class HealthzAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "/healthz" not in message and "/results/all" not in message


def configure_access_log_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, HealthzAccessLogFilter) for f in access_logger.filters):
        access_logger.addFilter(HealthzAccessLogFilter())


def start_api(debug: bool = False) -> FastAPI:
    if config.server.suppress_polling_logs:
        configure_access_log_filter()

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
    static_dir = Path(__file__).parent / "ui"
    if static_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(static_dir)), name="ui")

    # Serve index.html for the root path
    @app.get("/")
    async def serve_index():
        index_file = Path(__file__).parent / "ui" / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "HeliotrAPI Analysis. Visit /docs for API documentation"}

    if debug:

        @app.middleware("http")
        async def disable_cache(request, call_next):
            response = await call_next(request)

            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

            return response

    return app
