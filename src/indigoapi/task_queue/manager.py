import asyncio
import inspect
import logging
from datetime import datetime
from typing import Any, get_args, get_origin
from uuid import UUID

import numpy as np
from xrpd_toolbox.utils.messenger import DEFAULT_DII_PROCESSED_DESTINATION, Messenger

from indigoapi.analysis_core.registry import get_analysis
from indigoapi.models import AnalysisRequest, AnalysisResult
from indigoapi.utils.serialisers import serialise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def convert_value(value: Any, annotation: Any) -> Any:
    """
    Convert a JSON-deserialized value into the expected Python type
    based on a function parameter annotation.
    """

    if annotation is inspect.Parameter.empty:
        return value

    ann_str = str(annotation).lower()

    if annotation is np.ndarray or "ndarray" in ann_str or "numpy" in ann_str:
        return np.array(value, dtype=float)

    if annotation is int:
        return int(value)

    if annotation is float:
        return float(value)

    if annotation is bool:
        return bool(value)

    if annotation is str:
        return str(value)

    origin = get_origin(annotation)

    if origin is list:
        item_type = get_args(annotation)[0]

        return [convert_value(v, item_type) for v in value]

    if origin is tuple:
        item_types = get_args(annotation)

        return tuple(
            convert_value(v, t) for v, t in zip(value, item_types, strict=True)
        )

    if origin is dict:
        key_type, val_type = get_args(annotation)

        return {
            convert_value(k, key_type): convert_value(v, val_type)
            for k, v in value.items()
        }

    return value


def convert_inputs(inputs: dict, annotations: dict) -> dict:
    """
    Convert a dictionary of raw JSON inputs using
    a dictionary of parameter annotations.
    """

    converted = {}

    for key, value in inputs.items():
        annotation = annotations.get(key, inspect.Parameter.empty)

        converted[key] = convert_value(value, annotation)

    return converted


def get_function_annotations(func) -> dict:
    """
    Extract parameter annotations from a function.
    """

    sig = inspect.signature(func)

    return {name: param.annotation for name, param in sig.parameters.items()}


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

    async def worker(self):
        while True:
            job = await self.queue.get()

            try:
                analysis_fn = get_analysis(job.analysis_name)

                annotations = get_function_annotations(analysis_fn)
                converted_inputs = convert_inputs(job.inputs, annotations)
                result_value = await analysis_fn(**converted_inputs)

                # Convert numpy and other non-JSON-serializable types
                result_value = serialise(result_value)

                analysis_result = AnalysisResult(
                    request_id=job.request_id,
                    analysis_name=job.analysis_name,
                    status="completed",
                    result=result_value,
                    created_at=job.created_at,
                    finished_at=datetime.now(),
                )

            except Exception as e:
                analysis_result = AnalysisResult(
                    request_id=job.request_id,
                    analysis_name=job.analysis_name,
                    status="failed",
                    result=str(e),
                    created_at=job.created_at,
                    finished_at=datetime.now(),
                )

                if self.messenger is not None:
                    self.messenger.send_message(
                        DEFAULT_DII_PROCESSED_DESTINATION,
                        analysis_result.model_dump_json(),
                    )

            self.results[job.request_id] = analysis_result
            # store latest result
            self.latest_result = analysis_result
