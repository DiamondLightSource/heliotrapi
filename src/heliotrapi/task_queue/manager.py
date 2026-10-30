import asyncio
import contextvars
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from heliotrapi.analysis_core.async_func import CURRENT_CANCELLER, ThreadCanceller
from heliotrapi.analysis_core.registry import get_analysis
from heliotrapi.logger import logger
from heliotrapi.models import AnalysisRequest, AnalysisResponse, AnalysisResult
from heliotrapi.task_queue.store import ResultStore
from heliotrapi.utils.messenger import DEFAULT_DII_PROCESSED_DESTINATION, Messenger
from heliotrapi.utils.serialisers import deserialise, serialise
from heliotrapi.utils.slack_alerts import send_slack_failure


def convert_inputs(inputs: dict, annotations: dict) -> dict:
    """Convert raw JSON request values into typed Python arguments.

    This helper takes a JSON-style input dictionary from an analysis request
    and converts each value to the expected Python type using the given
    function parameter annotations.

    Args:
        inputs: Raw request inputs, typically from the JSON payload.
        annotations: A mapping from parameter names to type annotations.

    Returns:
        A new dictionary containing the converted values ready to be passed
        to the analysis function.

    Example:
        inputs = {"number": "5", "scale": "2.0"}
        annotations = {"number": int, "scale": float}
        result = convert_inputs(inputs, annotations)
        # result == {"number": 5, "scale": 2.0}
    """

    converted = {}

    for key, value in inputs.items():
        annotation = annotations.get(key, inspect.Parameter.empty)

        converted[key] = deserialise(value, annotation)

    return converted


def get_function_annotations(func) -> dict[str, Any]:
    """Read a function's signature and return its parameter type hints.

    This helper examines the target analysis function and builds a dictionary
    of parameter names to their annotations. The result is later used to
    convert and validate incoming request inputs.

    Args:
        func: The analysis function whose parameter annotations are required.

    Returns:
        A dictionary mapping each parameter name to its annotation object.

    Example:
        def analysis(number: int, scale: float = 1.0):
            return number * scale

        annotations = get_function_annotations(analysis)
        # annotations == {"number": int, "scale": float}
    """

    sig = inspect.signature(func)

    return {name: param.annotation for name, param in sig.parameters.items()}


def validate_inputs(func, inputs: dict):
    sig = inspect.signature(func)

    errors = []

    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        # Missing required parameter
        if name not in inputs and param.default is inspect.Parameter.empty:
            errors.append(f"Missing required parameter: {name}")
            continue

        if name not in inputs:
            continue

        value = inputs[name]
        annotation = param.annotation

        try:
            deserialise(value, annotation)

        except Exception as e:
            errors.append(f"Invalid value for '{name}': {e}")

    # Unknown extra parameters, unless the function takes **kwargs
    extra = set(inputs) - set(sig.parameters)
    has_var_kwargs = any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())

    if extra and not has_var_kwargs:
        errors.append(f"Unknown parameters: {sorted(extra)}")

    if errors:
        raise ValueError("\n".join(errors))


# That  db_path: str defaults to memory
# but Helm overrides it to /data/results.db, which is on the PVC


class QueueManager:
    def __init__(
        self,
        workers: int = 2,
        messenger: Messenger | None = None,
        webhook_url: str | None = None,
        db_path: str | Path = ":memory:",
    ):
        self.queue: asyncio.Queue[AnalysisRequest] = asyncio.Queue(maxsize=0)  # 0 = inf
        self.results = ResultStore(db_path)
        self.workers = workers
        self.messenger = messenger
        self.webhook_url = webhook_url
        # running analyses, so they can be cancelled
        self.running_tasks: dict[UUID, tuple[asyncio.Task, ThreadCanceller]] = {}
        # jobs cancelled before or while running, so the worker knows to skip them
        self.cancelled: set[UUID] = set()
        self.fail_interrupted_jobs()
        logger.info(self.queue)

    @property
    def latest_result(self) -> AnalysisResult | None:
        return self.results.latest_finished()

    @latest_result.setter
    def latest_result(self, result: AnalysisResult) -> None:
        assert result.request_id is not None
        self.results[result.request_id] = result

    def fail_interrupted_jobs(self):
        # the queue lives in memory, so jobs still running when the server
        # stopped will never finish - mark them failed
        for result in self.results.running():
            result.status = "failed"
            result.result = "Server restarted before the analysis finished"
            result.finished_at = datetime.now()
            assert result.request_id is not None
            self.results[result.request_id] = result

    async def enqueue(self, job: AnalysisRequest) -> AnalysisResponse:
        job.created_at = datetime.now()
        logger.info(job)

        pending_result = AnalysisResult(
            request_id=job.request_id,
            analysis_name=job.analysis_name,
            inputs=job.inputs,
            status="running",
            result=None,
            created_at=job.created_at,
            finished_at=None,
        )

        try:
            analysis_fn = get_analysis(job.analysis_name)  # will raise if no analysis
            validate_inputs(analysis_fn, job.inputs)  # will raise if inputs are invalid
            self.results[job.request_id] = pending_result
            await self.queue.put(job)
            analysis_response = AnalysisResponse(
                request_id=job.request_id,
                analysis_name=job.analysis_name,
                inputs=job.inputs,
                accepted=True,
            )

        except Exception as e:
            pending_result.status = "failed"
            pending_result.result = str(e)
            pending_result.finished_at = datetime.now()
            self.results[job.request_id] = pending_result

            analysis_response = AnalysisResponse(
                request_id=job.request_id,
                analysis_name=job.analysis_name,
                error=str(e),
                inputs=job.inputs,
                accepted=False,
            )

            # log the error and send alert to slack if configured
            logger.error(analysis_response)

            if self.webhook_url is not None:
                send_slack_failure(
                    webhook_url=self.webhook_url,
                    message=f"Job {job} failed: {str(e)}",
                )

        if self.messenger is not None and self.messenger.is_connected():
            self.messenger.send_message(
                DEFAULT_DII_PROCESSED_DESTINATION,
                analysis_response.model_dump_json(),
            )

        return analysis_response

    def cancel(self, request_id: UUID) -> AnalysisResult:
        """Cancel a queued or running job.

        Raises KeyError if the job doesn't exist, ValueError if it isn't running.
        Sync analyses are stopped by raising an exception in their thread, see
        ThreadCanceller for when that can be delayed.
        """
        result = self.results[request_id]

        if result.status != "running":
            raise ValueError(
                f"Job {request_id} can't be cancelled, its status is '{result.status}'"
            )

        self.cancelled.add(request_id)

        if request_id in self.running_tasks:
            task, canceller = self.running_tasks[request_id]
            task.cancel()  # stops async analyses
            canceller.cancel()  # stops sync analyses running in a thread

        result.status = "cancelled"
        result.result = "Cancelled by user"
        result.finished_at = datetime.now()
        self.results[request_id] = result

        logger.info(f"Job {request_id} cancelled")

        if self.messenger is not None and self.messenger.is_connected():
            self.messenger.send_message(
                DEFAULT_DII_PROCESSED_DESTINATION,
                result.model_dump_json(),
            )

        return result

    async def worker(self):
        while True:
            job = await self.queue.get()

            # cancelled while still in the queue
            if job.request_id in self.cancelled:
                self.cancelled.discard(job.request_id)
                self.queue.task_done()
                continue

            try:
                analysis_fn = get_analysis(job.analysis_name)
                annotations = get_function_annotations(analysis_fn)

                logger.info(annotations)

                # validate_inputs(analysis_fn, job.inputs)
                converted_inputs = convert_inputs(job.inputs, annotations)

                # run as a task so cancel() can stop it
                canceller = ThreadCanceller()
                context = contextvars.copy_context()
                context.run(CURRENT_CANCELLER.set, canceller)
                task = asyncio.create_task(
                    analysis_fn(**converted_inputs), context=context
                )
                self.running_tasks[job.request_id] = (task, canceller)
                try:
                    result_value = await task  # actually run job
                finally:
                    self.running_tasks.pop(job.request_id, None)

                # Convert numpy and other non-serializable types
                result_value = serialise(result_value)

                result = result_value
                status = "completed"
                finished_at = datetime.now()

            except asyncio.CancelledError:
                # if the job wasn't cancelled, the worker itself is shutting down
                if job.request_id not in self.cancelled:
                    raise
                # cancel() has already stored the cancelled result
                self.cancelled.discard(job.request_id)
                continue

            except Exception as e:
                result = str(e)
                status = "failed"
                finished_at = datetime.now()

                if self.webhook_url is not None:
                    send_slack_failure(
                        webhook_url=self.webhook_url,
                        message=f"Job {job} failed: {str(e)}",
                    )

            finally:
                self.queue.task_done()

            logger.info(
                f"Job {job.request_id} finished with status '{status}' and result: {result}"  # noqa
            )

            # get pending result and update with final status and result
            analysis_result: AnalysisResult = self.results[job.request_id]
            analysis_result.status = status
            analysis_result.result = result
            analysis_result.finished_at = finished_at

            self.results[job.request_id] = analysis_result

            if self.messenger is not None and self.messenger.is_connected():
                self.messenger.send_message(
                    DEFAULT_DII_PROCESSED_DESTINATION,
                    analysis_result.model_dump_json(),
                )
