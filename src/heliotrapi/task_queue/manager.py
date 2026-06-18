import asyncio
import inspect
from datetime import datetime
from typing import Any
from uuid import UUID

from heliotrapi.analysis_core.registry import get_analysis
from heliotrapi.logger import logger
from heliotrapi.models import AnalysisRequest, AnalysisResponse, AnalysisResult
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

    # Unknown extra parameters
    extra = set(inputs) - set(sig.parameters)

    if extra:
        errors.append(f"Unknown parameters: {sorted(extra)}")

    if errors:
        raise ValueError("\n".join(errors))


class QueueManager:
    def __init__(
        self,
        workers: int = 2,
        messenger: Messenger | None = None,
        slack_webhook_url: str | None = None,
    ):
        self.queue: asyncio.Queue[AnalysisRequest] = asyncio.Queue(maxsize=0)  # 0 = inf
        self.results: dict[UUID, AnalysisResult] = {}
        self.workers = workers
        self.latest_result: AnalysisResult | None = None
        self.messenger = messenger
        self.slack_webhook_url = slack_webhook_url
        logger.info(self.queue)

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
            self.latest_result = pending_result

            analysis_response = AnalysisResponse(
                request_id=job.request_id,
                analysis_name=job.analysis_name,
                details=str(e),
                inputs=job.inputs,
                accepted=False,
            )

            # log the error and send alert to slack if configured
            logger.error(analysis_response)

            if self.slack_webhook_url is not None:
                send_slack_failure(
                    webhook_url=self.slack_webhook_url,
                    message=f"Job {job} failed: {str(e)}",
                )

        if self.messenger is not None:
            self.messenger.send_message(
                DEFAULT_DII_PROCESSED_DESTINATION,
                analysis_response.model_dump_json(),
            )

        return analysis_response

    async def worker(self):
        while True:
            job = await self.queue.get()

            try:
                analysis_fn = get_analysis(job.analysis_name)
                annotations = get_function_annotations(analysis_fn)

                logger.info(annotations)

                # validate_inputs(analysis_fn, job.inputs)
                converted_inputs = convert_inputs(job.inputs, annotations)

                result_value = await analysis_fn(**converted_inputs)  # actually run job

                # Convert numpy and other non-serializable types
                result_value = serialise(result_value)

                result = result_value
                status = "completed"
                finished_at = datetime.now()

            except Exception as e:
                result = str(e)
                status = "failed"
                finished_at = datetime.now()

                if self.slack_webhook_url is not None:
                    send_slack_failure(
                        webhook_url=self.slack_webhook_url,
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
            # store latest result
            self.latest_result = analysis_result

            if self.messenger is not None:
                self.messenger.send_message(
                    DEFAULT_DII_PROCESSED_DESTINATION,
                    analysis_result.model_dump_json(),
                )
