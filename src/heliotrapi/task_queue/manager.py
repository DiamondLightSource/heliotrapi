import asyncio
import inspect
from datetime import datetime
from typing import Annotated, Any, get_args, get_origin, get_type_hints
from uuid import UUID

import numpy as np
from pydantic import BeforeValidator, ConfigDict, create_model
from xrpd_toolbox.utils.messenger import DEFAULT_DII_PROCESSED_DESTINATION, Messenger

from heliotrapi import logger
from heliotrapi.analysis_core.registry import get_analysis
from heliotrapi.models import AnalysisRequest, AnalysisResponse, AnalysisResult
from heliotrapi.utils.serialisers import deserialise, serialise


def wrap_numpy(tp):
    if tp is np.ndarray:
        return Annotated[np.ndarray, BeforeValidator(lambda v: np.asarray(v))]
    return tp


def coerce_list_union(v):
    # handles list[int | float]
    if isinstance(v, list):
        return [float(x) for x in v]
    return v


def wrap_annotation(tp):
    origin = get_origin(tp)

    # intercept problematic pattern: list[int | float]
    if origin is list:
        args = get_args(tp)

        if args:
            inner = args[0]

            # detect Union inside list
            if get_origin(inner) is None and hasattr(inner, "__args__"):
                return Annotated[list, BeforeValidator(coerce_list_union)]

    return tp


def build_model(func):
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    fields = {}

    for name, param in sig.parameters.items():
        annotation = hints.get(name, Any)

        # 🔥 KEY FIX
        annotation = wrap_numpy(annotation)

        default = param.default if param.default is not inspect.Parameter.empty else ...

        fields[name] = (annotation, default)

    return create_model(
        func.__name__ + "Model",
        __config__=ConfigDict(arbitrary_types_allowed=True),
        **fields,
    )


def convert_inputs(inputs: dict, func):
    module = build_model(func)  # MUST be a class
    obj = module(**inputs)  # validation + coercion
    return obj.model_dump()


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
    def __init__(self, workers: int = 2, messenger: Messenger | None = None):
        self.queue: asyncio.Queue[AnalysisRequest] = asyncio.Queue(maxsize=0)  # 0 = inf
        self.results: dict[UUID, AnalysisResult] = {}
        self.workers = workers
        self.latest_result: AnalysisResult | None = None
        self.messenger = messenger
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
            logger.error(analysis_response)

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
                # annotations = get_function_annotations(analysis_fn)

                converted_inputs = convert_inputs(job.inputs, analysis_fn)
                # logger.info(annotations)

                # validate_inputs(analysis_fn, job.inputs)
                # converted_inputs = convert_inputs(job.inputs, annotations)

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
