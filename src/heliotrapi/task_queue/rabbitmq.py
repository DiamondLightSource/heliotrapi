import asyncio
import json
import threading
import time

import stomp

from heliotrapi import logger
from heliotrapi.analysis_core.decorator import (
    FINISHED_NEXUS_ANALYSIS_NAME,
    START_MESSAGE_ANALYSIS_NAME,
    STARTED_NEXUS_ANALYSIS_NAME,
    STOP_MESSAGE_ANALYSIS_NAME,
    UPDATED_NEXUS_ANALYSIS_NAME,
)
from heliotrapi.analysis_core.registry import ANALYSIS_REGISTRY
from heliotrapi.models import AnalysisRequest
from heliotrapi.task_queue import QueueManager
from heliotrapi.task_queue.message_models import (
    NexusMessage,
    StartMessage,
    StopMessage,
    validate_stomp_message,
)

TIMEOUT = 10
MAX_RECONNECT_DELAY = 300  # cap backoff at 5 minutes


class _StompListener(stomp.ConnectionListener):
    def __init__(self, queue_manager: QueueManager, loop: asyncio.AbstractEventLoop):
        self.queue_manager = queue_manager
        self.loop = loop

    def stomp_message_to_request(self, data: dict) -> AnalysisRequest | None:
        """Parse a STOMP message body into an AnalysisRequest, or None if the
        message should be ignored by the queuer.

        Dispatch is based on a small set of distinguishing keys per message
        type. Order matters only in that more specific/required key-sets are
        checked first to reduce ambiguity between message shapes.
        """
        validated_model = validate_stomp_message(data)

        if isinstance(validated_model, AnalysisRequest):
            return validated_model

        elif isinstance(validated_model, StartMessage):
            # need to ignore because event_model BaseModels allow extra and
            # so BlueAPI spits out stuff not present in the BaseModel

            scan_file = validated_model.doc.scan_file
            plan_name = validated_model.doc.plan_name
            logger.info(f"StartMessage Received. {scan_file=} {plan_name=}")
            return AnalysisRequest(
                analysis_name=START_MESSAGE_ANALYSIS_NAME,
                inputs={"message": validated_model},
            )

        elif isinstance(validated_model, StopMessage):
            # need to ignore because event_model BaseModels allow extra and
            # so BlueAPI spits out stuff not present in the BaseModel
            exit_status = validated_model.doc.exit_status  # type: ignore
            logger.info(f"StopMessage Received. {exit_status=}")
            return AnalysisRequest(
                analysis_name=STOP_MESSAGE_ANALYSIS_NAME,
                inputs={"message": validated_model},
            )
        elif isinstance(validated_model, NexusMessage):
            status = validated_model.status
            filepath = validated_model.filePath
            logger.info(f"NexusMessage Received. {status=} {filepath=}")

            if status == "STARTED":
                if STARTED_NEXUS_ANALYSIS_NAME in ANALYSIS_REGISTRY:
                    return AnalysisRequest(
                        analysis_name=STARTED_NEXUS_ANALYSIS_NAME,
                        inputs={"message": validated_model},
                    )

            elif status == "UPDATED":
                if UPDATED_NEXUS_ANALYSIS_NAME in ANALYSIS_REGISTRY:
                    return AnalysisRequest(
                        analysis_name=UPDATED_NEXUS_ANALYSIS_NAME,
                        inputs={"message": validated_model},
                    )

            elif status == "FINISHED":
                if FINISHED_NEXUS_ANALYSIS_NAME in ANALYSIS_REGISTRY:
                    return AnalysisRequest(
                        analysis_name=FINISHED_NEXUS_ANALYSIS_NAME,
                        inputs={"message": validated_model},
                    )

        else:
            return None

    def on_connected(self, frame):
        logger.info("RabbitMQ connected")

    def on_disconnected(self):
        logger.warning("RabbitMQ connection lost")

    def on_error(self, frame):
        logger.error(f"STOMP error: {frame.body}")

    def on_message(self, frame):
        try:
            data = json.loads(frame.body)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message body: {frame.body} due to: {e}")
            return

        try:
            job = self.stomp_message_to_request(data)
        except Exception as e:
            logger.error(f"Failed to parse message: {frame.body} due to: {e}")
            return

        if isinstance(job, AnalysisRequest):
            logger.info(f"RabbitMQ job received: {job.request_id}")
            asyncio.run_coroutine_threadsafe(
                self.queue_manager.enqueue(job),
                self.loop,
            )


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
        self._conn: stomp.Connection | None = None

    async def start(self):
        loop = asyncio.get_running_loop()

        self.thread = threading.Thread(
            target=self._run,
            args=(loop,),
            daemon=True,
        )

        self.thread.start()

        logger.info("RabbitMQ listener thread started")

    def stop(self, timeout: float = TIMEOUT):
        """Signal the listener thread to stop and disconnect cleanly."""
        self.running = False

        conn = self._conn
        if conn is not None and conn.is_connected():
            try:
                conn.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting from RabbitMQ: {e}")

        if self.thread is not None:
            self.thread.join(timeout=timeout)

    def _run(self, loop: asyncio.AbstractEventLoop):

        attempt = 0

        while self.running:
            attempt += 1

            logger.info(
                f"RabbitMQ connection attempt {attempt} to {self.host}:{self.port}"
            )

            conn: stomp.Connection | None = None
            try:
                conn = stomp.Connection(
                    [(self.host, self.port)],
                    heartbeats=(TIMEOUT * 1000, TIMEOUT * 1000),  # heartbeat in ms
                    timeout=TIMEOUT,
                )
                self._conn = conn

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

                while conn.is_connected() and self.running:
                    time.sleep(1)

            except Exception as e:
                logger.warning(f"RabbitMQ connection failed: {e}")

            finally:
                if conn is not None and conn.is_connected():
                    try:
                        conn.disconnect()
                    except Exception as e:
                        logger.warning(f"Error disconnecting from RabbitMQ: {e}")
                self._conn = None

            if not self.running:
                break

            delay_time = min(TIMEOUT + attempt, MAX_RECONNECT_DELAY)
            logger.info(f"Waiting {delay_time}s before next reconnect")
            time.sleep(delay_time)
