import inspect
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from redis.asyncio import Redis

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
    """Dispatches analysis jobs through a Redis-backed queue.

    State (the job queue, per-job results, and the latest result) lives in
    Redis rather than process memory, so it's shared correctly across
    multiple OS worker processes (see src/heliotrapi/asgi.py and
    __main__.py's Gunicorn branch) rather than being private to whichever
    process happened to accept a given request.
    """

    def __init__(
        self,
        redis_client: Redis,
        workers: int = 2,
        messenger: Messenger | None = None,
        slack_webhook_url: str | None = None,
        key_prefix: str = "heliotrapi",
        results_ttl_seconds: int = 3600,
    ):
        self._redis = redis_client
        self.workers = workers
        self.messenger = messenger
        self.slack_webhook_url = slack_webhook_url
        self.key_prefix = key_prefix
        self.results_ttl_seconds = results_ttl_seconds
        logger.info(f"QueueManager using Redis queue '{self._queue_key}'")

    @property
    def _queue_key(self) -> str:
        return f"{self.key_prefix}:queue:jobs"

    @property
    def _latest_key(self) -> str:
        return f"{self.key_prefix}:result:latest"

    @property
    def _index_key(self) -> str:
        return f"{self.key_prefix}:results:index"

    def _result_key(self, request_id: UUID) -> str:
        return f"{self.key_prefix}:result:{request_id}"

    async def _store_result(self, result: AnalysisResult) -> None:
        payload = result.model_dump_json()
        created_at = result.created_at or datetime.now()

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(
                self._result_key(result.request_id),
                payload,
                ex=self.results_ttl_seconds,
            )
            pipe.set(self._latest_key, payload)
            pipe.zadd(self._index_key, {str(result.request_id): created_at.timestamp()})
            await pipe.execute()

    async def get_result(self, request_id: UUID) -> AnalysisResult | None:
        payload = await self._redis.get(self._result_key(request_id))
        if payload is None:
            return None
        return AnalysisResult.model_validate_json(payload)

    async def get_latest_result(self) -> AnalysisResult | None:
        payload = await self._redis.get(self._latest_key)
        if payload is None:
            return None
        return AnalysisResult.model_validate_json(payload)

    async def get_all_results(self) -> list[AnalysisResult]:
        ids = await self._redis.zrevrangebyscore(self._index_key, "+inf", "-inf")

        results = []
        expired = []

        for request_id in ids:
            payload = await self._redis.get(self._result_key(UUID(request_id)))
            if payload is None:
                # TTL already expired this result; drop the stale index entry.
                expired.append(request_id)
                continue
            results.append(AnalysisResult.model_validate_json(payload))

        if expired:
            await self._redis.zrem(self._index_key, *expired)

        return results

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
            await self._store_result(pending_result)
            await self._redis.lpush(self._queue_key, job.model_dump_json())
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
            await self._store_result(pending_result)

            analysis_response = AnalysisResponse(
                request_id=job.request_id,
                analysis_name=job.analysis_name,
                error=str(e),
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

        if self.messenger is not None and self.messenger.is_connected():
            self.messenger.send_message(
                DEFAULT_DII_PROCESSED_DESTINATION,
                analysis_response.model_dump_json(),
            )

        return analysis_response

    async def worker(self) -> None:
        while True:
            # redis-py's stubs type this as bytes|str regardless of
            # decode_responses, since that flag isn't tracked statically.
            item = await self._redis.brpop([self._queue_key], timeout=5)
            if item is None:
                continue  # timed out waiting for a job; loop and block again

            _, payload = item
            job = AnalysisRequest.model_validate_json(payload)
            await self._process_job(job)

    async def _process_job(self, job: AnalysisRequest) -> AnalysisResult:
        """Run a single dequeued job and store its result. Split out of
        worker() so it can be unit-tested directly, without a real blocking
        BRPOP loop to spin up and tear down."""
        result: Any
        status: Literal["completed", "failed"]

        try:
            analysis_fn = get_analysis(job.analysis_name)
            annotations = get_function_annotations(analysis_fn)

            logger.info(annotations)

            converted_inputs = convert_inputs(job.inputs, annotations)

            result_value = await analysis_fn(**converted_inputs)  # actually run job

            # Convert numpy and other non-serializable types
            result = serialise(result_value)
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

        logger.info(
            f"Job {job.request_id} finished with status '{status}' and result: {result}"  # noqa
        )

        # preserve the original created_at recorded at enqueue time
        pending_result = await self.get_result(job.request_id)
        created_at = pending_result.created_at if pending_result else job.created_at

        analysis_result = AnalysisResult(
            request_id=job.request_id,
            analysis_name=job.analysis_name,
            inputs=job.inputs,
            status=status,
            result=result,
            created_at=created_at,
            finished_at=finished_at,
        )

        await self._store_result(analysis_result)

        if self.messenger is not None and self.messenger.is_connected():
            self.messenger.send_message(
                DEFAULT_DII_PROCESSED_DESTINATION,
                analysis_result.model_dump_json(),
            )

        return analysis_result
