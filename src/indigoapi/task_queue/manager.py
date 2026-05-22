import asyncio
import inspect
import logging
from datetime import datetime
from uuid import UUID

from xrpd_toolbox.utils.messenger import DEFAULT_DII_PROCESSED_DESTINATION, Messenger

from indigoapi.analysis_core.registry import get_analysis
from indigoapi.models import AnalysisRequest, AnalysisResult
from indigoapi.utils.serialisers import deserialise, serialise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def convert_inputs(inputs: dict, annotations: dict) -> dict:
    """
    Convert a dictionary of raw JSON inputs using
    a dictionary of parameter annotations.
    """

    converted = {}

    for key, value in inputs.items():
        annotation = annotations.get(key, inspect.Parameter.empty)

        converted[key] = deserialise(value, annotation)

    return converted


def get_function_annotations(func) -> dict:
    """
    Extract parameter annotations from a function.
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
    def __init__(self, workers: int = 2, messenger: Messenger | None = None):
        self.queue: asyncio.Queue[AnalysisRequest] = asyncio.Queue(maxsize=0)  # 0 = inf
        self.results: dict[UUID, AnalysisResult] = {}
        self.workers = workers
        self.latest_result: AnalysisResult | None = None
        self.messenger = messenger

        logger.info(self.queue)

    async def enqueue(self, job: AnalysisRequest):
        job.created_at = datetime.now()
        logger.info(job)

        pending_result = AnalysisResult(
            request_id=job.request_id,
            analysis_name=job.analysis_name,
            status="running",
            result=None,
            created_at=job.created_at,
            finished_at=None,
        )

        self.results[job.request_id] = pending_result

        await self.queue.put(job)

        return pending_result

    async def worker(self):
        while True:
            job = await self.queue.get()

            try:
                analysis_fn = get_analysis(job.analysis_name)
                annotations = get_function_annotations(analysis_fn)

                validate_inputs(analysis_fn, job.inputs)

                converted_inputs = convert_inputs(job.inputs, annotations)
                result_value = await analysis_fn(**converted_inputs)

                # Convert numpy and other non-JSON-serializable types
                result_value = serialise(result_value)

                result = result_value
                status = "completed"
                finished_at = datetime.now()

            except Exception as e:
                result = str(e)
                status = "failed"
                finished_at = datetime.now()

            finally:
                self.queue.task_done()

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
