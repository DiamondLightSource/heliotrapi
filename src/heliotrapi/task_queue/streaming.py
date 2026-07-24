import asyncio
from collections.abc import Callable
from typing import Any

from heliotrapi.analysis_core.registry import get_analysis
from heliotrapi.logger import logger
from heliotrapi.models import (
    AnalysisStreamRequest,
    StreamUpdate,
)
from heliotrapi.task_queue.manager import convert_inputs, get_function_annotations


async def run_stream_analysis(
    analysis_fn: Callable,
    inputs: dict[str, Any],
    update_interval: float = 0.1,
    max_iterations: int = 100,
):

    iter = 0

    while iter < max_iterations:
        result_value = await analysis_fn(**inputs)  # actually run job
        # assert isinstance(result_value, (float | int))

        update = StreamUpdate(x=iter, y=result_value)

        iter = iter + 1

        yield update.model_dump()

        await asyncio.sleep(update_interval)


async def create_stream(job: AnalysisStreamRequest):
    analysis_fn = get_analysis(job.analysis_name)
    annotations = get_function_annotations(analysis_fn)
    converted_inputs = convert_inputs(job.inputs, annotations)
    update_interval = job.update_interval
    max_iterations = job.max_iterations

    logger.info(job.inputs)

    async for point in run_stream_analysis(
        analysis_fn=analysis_fn,
        inputs=converted_inputs,
        update_interval=update_interval,
        max_iterations=max_iterations,
    ):
        yield point
