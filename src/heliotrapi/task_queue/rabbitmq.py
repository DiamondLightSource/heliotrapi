import asyncio
import json
import threading
import time
from enum import StrEnum
from typing import Any, Literal

import stomp
from pydantic import (
    BaseModel,
    Field,
)

from heliotrapi import logger
from heliotrapi.models import AnalysisRequest
from heliotrapi.task_queue import QueueManager

TIMEOUT = 10

####### gda messages


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


############# bluesky


class WorkerState(StrEnum):
    """
    The state of the Worker.
    """

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    HALTING = "HALTING"
    STOPPING = "STOPPING"
    ABORTING = "ABORTING"
    SUSPENDING = "SUSPENDING"
    PANICKED = "PANICKED"
    UNKNOWN = "UNKNOWN"


class TaskResult(BaseModel):
    """
    Serializable wrapper around the result of a plan

    If the result is not serializable, the result will be None but the type
    will be the name of the type. If the result is actually None, the type will
    be 'NoneType'.
    """

    outcome: Literal["success"] = "success"
    """Discriminant for serialization"""
    result: Any = Field(None)
    """The serialized result (or None if it is not serializable)"""
    type: str
    """The type of the result"""


class TaskError(BaseModel):
    """Wrapper around an exception raised by a plan"""

    outcome: Literal["error"] = "error"
    """Discriminant for serialization"""
    type: str
    """The class of exception"""
    message: str
    """The message of the raised exception"""


class TaskStatus(BaseModel):
    """
    Status of a task the worker is running.
    """

    task_id: str
    result: TaskResult | TaskError | None = Field(None, discriminator="outcome")
    task_complete: bool
    task_failed: bool


class WorkerEvent(BaseModel):
    """
    Event describing the state of the worker and any tasks it's running.
    Includes error and warning information.
    """

    state: WorkerState
    task_status: TaskStatus | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def is_error(self) -> bool:
        return (self.task_status is not None and self.task_status.task_failed) or bool(
            self.errors
        )

    def is_complete(self) -> bool:
        return self.task_status is not None and self.task_status.task_complete


def worker_event_to_job(worker_event) -> AnalysisRequest | None:

    # TODO: This is a placeholder -
    # need to define how WorkerEvents map to AnalysisRequests

    _ = AnalysisRequest(analysis_name="", inputs={})

    return None


class _StompListener(stomp.ConnectionListener):
    def __init__(self, queue_manager: QueueManager, loop: asyncio.AbstractEventLoop):
        self.queue_manager = queue_manager
        self.loop = loop

    def parse_stomp_message(self, data: dict) -> AnalysisRequest | None:
        """ "parse job converts a message over rabbitmq into a AnalysisRequest or None,
        if None the queuer will ignore"""

        if "analysis_name" in data:
            # a analysis reequest sent via rabbitmq
            return AnalysisRequest.model_validate(data)

        elif "event_type" in data and "task_id" in data:
            # data_event = data
            logger.info("Received data event")
            return None

        elif "status" in data and "filePath" in data and "visitDirectory" in data:
            gda_scan_message = ScanMessage.model_validate(
                data
            )  # just to validate the message format
            logger.info(
                f"Received GDA scan message: {gda_scan_message.filePath}, {gda_scan_message.scanNumber}, {gda_scan_message.status}"  # noqa
            )
            return None

        elif "state" in data and "task_status" in data:
            # bluesky event
            worker_event = WorkerEvent.model_validate(data)

            logger.info(
                f"Bluesky worker event: {worker_event.state} {worker_event.task_status}"
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

            job = self.parse_stomp_message(data)

            if isinstance(job, AnalysisRequest):
                logger.info(f"RabbitMQ job received: {job.request_id}")

                asyncio.run_coroutine_threadsafe(
                    self.queue_manager.enqueue(job),
                    self.loop,
                )
            else:
                pass

        except Exception as e:
            logger.error(f"Failed to process message:{frame.body} due to: {e}")


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
