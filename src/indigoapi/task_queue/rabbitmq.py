import asyncio
import json
import logging
import threading
import time
from typing import Any

import stomp
from pydantic import BaseModel, Field

from indigoapi.models import AnalysisRequest
from indigoapi.task_queue import QueueManager

logger = logging.getLogger(__name__)

TIMEOUT = 10


class ProcessingRequest(BaseModel):
    # empty dict in your example, so keep flexible
    model_config = {"extra": "allow"}


class ScanMessage(BaseModel):
    status: str
    filePath: str  # noqa: N815 - because this is gda
    visitDirectory: str  # noqa: N815 - because this is gda
    swmrStatus: str  # noqa: N815 - because this is gda

    scanNumber: int  # noqa: N815 - because this is gda
    scanDimensions: list[int]  # noqa: N815 - because this is gda

    scannables: list[Any] = Field(default_factory=list)
    detectors: list[Any] = Field(default_factory=list)

    percentageComplete: float  # noqa: N815 - because this is gda

    processingRequest: ProcessingRequest = Field(default_factory=ProcessingRequest)  # noqa: N815 - because this is gda


def worker_event_to_job(worker_event) -> AnalysisRequest:

    # TODO: This is a placeholder -
    # need to define how WorkerEvents map to AnalysisRequests

    return AnalysisRequest(analysis_name="", inputs={})


class _StompListener(stomp.ConnectionListener):
    def __init__(self, queue_manager: QueueManager, loop: asyncio.AbstractEventLoop):
        self.queue_manager = queue_manager
        self.loop = loop

    def parse_job(self, data: dict) -> AnalysisRequest | None:

        if "analysis_name" in data:
            return AnalysisRequest.model_validate(data)

        elif "event_type" in data and "task_id" in data:
            data_event = data
            logger.info(f"Received data event: {data_event}")
            logger.info("Will ignore...")
            return None

        elif "status" in data and "filePath" in data and "visitDirectory" in data:
            gda_scan_message = ScanMessage.model_validate(
                data
            )  # just to validate the message format
            logger.info(f"Received GDA scan message: {gda_scan_message}")
            logger.info("Will ignore...")
            return None

        elif "state" in data and "task_status" in data:
            worker_event = data

            if (
                worker_event["task_status"] is not None
                and worker_event["task_status"]["task_complete"]
            ):
                return worker_event_to_job(worker_event)
            else:
                logger.info(
                    f"Received non-complete WorkerEvent: {worker_event['task_status']}"
                )
                return None

        else:
            logger.info(f"Not a valid job received: {data}")

    def on_connected(self, frame):
        logger.info("RabbitMQ connected")

    def on_disconnected(self):
        logger.warning("RabbitMQ connection lost")

    def on_error(self, frame):
        logger.error(f"STOMP error: {frame.body}")

    def on_message(self, frame):
        try:
            data = json.loads(frame.body)

            job = AnalysisRequest.model_validate(data)

            logger.info(f"RabbitMQ job received: {job.request_id}")

            asyncio.run_coroutine_threadsafe(
                self.queue_manager.enqueue(job),
                self.loop,
            )

        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            logger.error(f"Failed message: {frame.body}")


class RabbitMQListener:
    def __init__(
        self,
        queue_manager: QueueManager,
        host: str,
        port: int,
        username: str,
        password: str,
        destinations: list[str],
    ):
        self.queue_manager = queue_manager
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.destinations = destinations

        self.running = True
        self.thread: threading.Thread | None = None

    async def start(self):
        loop = asyncio.get_running_loop()

        self.thread = threading.Thread(
            target=self._run,
            args=(loop,),
            daemon=True,
        )

        self.thread.start()

        logger.info("RabbitMQ listener thread started")

    def _run(self, loop: asyncio.AbstractEventLoop):

        attempt = 0

        while self.running:
            attempt += 1

            logger.info(
                f"RabbitMQ connection attempt {attempt} to {self.host}:{self.port}"
            )

            try:
                conn = stomp.Connection(
                    [(self.host, self.port)],
                    heartbeats=(TIMEOUT * 1000, TIMEOUT * 1000),  # heartbeat in in ms
                    timeout=TIMEOUT,
                )

                listener = _StompListener(
                    self.queue_manager,
                    loop,
                )
                conn.set_listener("", listener)
                conn.connect(self.username, self.password, wait=True)

                for i, dest in enumerate(self.destinations):
                    conn.subscribe(destination=dest, id=str(i), ack="auto")
                    logger.info(f"Subscribed to {dest}")

                if conn.is_connected():
                    attempt = 0  # reset attempt to 0 after successful connection

                while conn.is_connected():
                    time.sleep(1)

            except Exception as e:
                logger.warning(f"RabbitMQ connection failed: {e}")
                logger.info(
                    f"RabbitMQ connection attempt {attempt} to {self.host}:{self.port}"
                )
                delay_time = TIMEOUT + attempt

                logger.info(f" Waiting {delay_time}s before next reconnect")
                time.sleep(delay_time)
