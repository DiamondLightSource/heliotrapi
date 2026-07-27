"""Interface for `python -m heliotrapi`."""

import asyncio
import contextlib
import importlib
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

import heliotrapi
from heliotrapi import redis_service
from heliotrapi._version import __version__
from heliotrapi.analysis_core.loader import load_analyses, load_plugins
from heliotrapi.api.endpoints import HEALTH_ROUTE, RESULTS_ALL_ROUTE
from heliotrapi.api.routes import ROUTER
from heliotrapi.config import Config
from heliotrapi.logger import logger
from heliotrapi.task_queue import QueueManager, RabbitMQListener, SingleInstanceLock
from heliotrapi.utils.messenger import Messenger

config: Config = Config.load_config()


global MODULE_NAMES

MODULE_NAMES: list[str] = []  # currently empty


def initialize_analyses(register_all: bool = False):
    """Load built-in analyses and user plugins. Call during server startup."""

    package = importlib.import_module("heliotrapi.analyses")
    MODULE_NAMES.extend(load_analyses(package))  # add packages from load_analyses

    config = Config.load_config()
    load_plugins(config, register_all=register_all)


@dataclass
class _RabbitMQRuntime:
    """The listener plus the background task that guards it with a lock so
    only one uvicorn.workers process runs it at a time."""

    listener: RabbitMQListener
    lock_task: asyncio.Task


def _start_rabbitmq(
    config: Config, queue_manager: QueueManager, redis_client: Redis
) -> _RabbitMQRuntime:
    listener = RabbitMQListener(
        queue_manager=queue_manager,
        host=config.rabbitmq.host,
        port=config.rabbitmq.port,
        username=config.rabbitmq.username,
        password=config.rabbitmq.password,
        destinations=config.rabbitmq.destinations,
    )

    # STOMP topic subscriptions are pub/sub, so with multiple uvicorn.workers
    # every process would otherwise receive and enqueue every message. Only
    # the process holding this lock runs the listener; if it dies, the lock
    # expires and a sibling takes over.
    lock_config = config.rabbitmq.listener_lock
    lock = SingleInstanceLock(
        redis_client,
        lock_key=f"{config.redis.key_prefix}:rabbitmq:listener-lock",
        ttl_seconds=lock_config.ttl_seconds,
        renew_interval_seconds=lock_config.renew_interval_seconds,
        retry_interval_seconds=lock_config.retry_interval_seconds,
    )
    lock_task = asyncio.create_task(
        lock.run_while_held(
            on_acquire=listener.start,
            on_lose=lambda: asyncio.to_thread(listener.stop),
        )
    )
    return _RabbitMQRuntime(listener=listener, lock_task=lock_task)


async def _stop_rabbitmq(rabbitmq: _RabbitMQRuntime | None) -> None:
    if rabbitmq is None:
        return
    rabbitmq.lock_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await rabbitmq.lock_task


@asynccontextmanager
async def lifespan(app: FastAPI):

    redis_client = redis_service.build_client(config)

    messenger = (
        Messenger(
            host=config.rabbitmq.host,
            port=config.rabbitmq.port,
            username=config.rabbitmq.username,
            password=config.rabbitmq.password,
            auto_subscribe=False,
        )
        if config.rabbitmq.enabled
        else None
    )

    queue_manager = QueueManager(
        redis_client=redis_client,
        workers=config.queue.workers,
        messenger=messenger,
        slack_webhook_url=config.alerts.slack_webhook_url
        if config.alerts.slack_webhook_url != ""
        else None,
        key_prefix=config.redis.key_prefix,
        results_ttl_seconds=config.results.ttl_seconds,
    )

    worker_tasks = [
        asyncio.create_task(queue_manager.worker())
        for _ in range(queue_manager.workers)
    ]

    rabbitmq = (
        _start_rabbitmq(config, queue_manager, redis_client)
        if config.rabbitmq.enabled
        else None
    )

    app.state.queue_manager = queue_manager
    app.state.config = config

    logging.info("API started")

    yield

    logging.info("Shutting down")

    for task in worker_tasks:
        task.cancel()

    await _stop_rabbitmq(rabbitmq)
    await redis_client.aclose()


class HealthzAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return HEALTH_ROUTE not in message and RESULTS_ALL_ROUTE not in message


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
