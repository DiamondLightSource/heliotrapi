import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute

from heliotrapi.analysis_core.registry import get_analysis, list_analyses
from heliotrapi.api.endpoints import (
    ANALYSE_ROUTE,
    ANALYSES_ROUTE,
    ENDPOINTS_ROUTE,
    HEALTH_ROUTE,
    RESULT_BY_ID_ROUTE,
    RESULT_LATEST_ROUTE,
    RESULTS_ALL_ROUTE,
    STREAM_ROUTE,
)
from heliotrapi.logger import logger
from heliotrapi.models import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisResult,
    StreamUpdate,
)
from heliotrapi.task_queue import QueueManager
from heliotrapi.task_queue.manager import convert_inputs, get_function_annotations

ROUTER = APIRouter()


@ROUTER.get(HEALTH_ROUTE)
async def health():
    return {"status": "ok"}


def annotation_to_str(annotation) -> str:
    """Convert a Python annotation to a clean, readable string."""
    if annotation is inspect.Parameter.empty:
        return "Any"
    # Prefer __name__ for plain types (float, int, str, bool, ndarray, ...)
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    # Fallback for generics like list[float], Optional[str], etc.
    return str(annotation)


@ROUTER.get(ANALYSES_ROUTE)
async def available_analyses() -> list[dict[str, Any]]:
    analyses_info = []
    for name in list_analyses():
        func = get_analysis(name)
        sig = inspect.signature(func)
        params = []
        for p in sig.parameters.values():
            params.append(
                {
                    "name": p.name,
                    "default": repr(p.default)
                    if p.default != inspect.Parameter.empty
                    else None,
                    "annotation": annotation_to_str(p.annotation),
                }
            )
        analyses_info.append(
            {
                "name": name,
                "parameters": params,
                "annotations": annotation_to_str(sig.return_annotation),
                "docstring": func.__doc__ or "",
            }
        )
    return analyses_info


@ROUTER.post(ANALYSE_ROUTE)
async def analyse(request: Request, job: AnalysisRequest) -> AnalysisResponse:

    logger.info(
        f"Received analysis request from host: {request.headers.get('Host')} | agent: {request.headers['user-agent']}"  # noqa
    )

    try:
        get_analysis(job.analysis_name)
        queue: QueueManager = request.app.state.queue_manager
        analysis_response = await queue.enqueue(job)
        return analysis_response
    except Exception as e:
        return AnalysisResponse(
            request_id=job.request_id,
            analysis_name=job.analysis_name,
            inputs=job.inputs,
            error=str(e),
            accepted=False,
        )


@ROUTER.get(RESULT_LATEST_ROUTE, response_model=AnalysisResult)
async def get_latest_result(request: Request) -> AnalysisResult:

    queue_manager = request.app.state.queue_manager

    if queue_manager.latest_result is None:
        raise HTTPException(status_code=404, detail="No results yet")

    return queue_manager.latest_result


@ROUTER.get(RESULT_BY_ID_ROUTE)
async def result(request: Request, request_id: UUID):
    queue: QueueManager = request.app.state.queue_manager
    if request_id not in queue.results:
        raise HTTPException(404, "Result not found")
    result = queue.results[request_id]
    return result


@ROUTER.get(ENDPOINTS_ROUTE)
async def get_endpoints():
    return [
        {
            "path": route.path,
            "methods": list(route.methods),
            "name": route.name,
        }
        for route in ROUTER.routes
        if isinstance(route, APIRoute)
    ]


@ROUTER.get(RESULTS_ALL_ROUTE)
async def get_all_results(request: Request):
    queue: QueueManager = request.app.state.queue_manager
    # Return all jobs (pending, running, completed, failed), sorted by created_at
    results = list(queue.results.values())
    results.sort(key=lambda r: getattr(r, "created_at", None) or 0, reverse=True)
    return results


async def run_analysis(analysis_fn: Callable, inputs: dict[str, Any]):

    t = 0.0

    while t < 20:
        await asyncio.sleep(0.1)
        t += 0.1

        result_value = await analysis_fn(**inputs)  # actually run job
        assert isinstance(result_value, (float | int))

        update = StreamUpdate(x=t, y=result_value)

        yield update.model_dump()


@ROUTER.get(STREAM_ROUTE)
async def stream(request: Request, job: AnalysisRequest):
    """
    Server-Sent Events endpoint
    """

    logger.info(job.request_id)

    analysis_fn = get_analysis(job.analysis_name)
    annotations = get_function_annotations(analysis_fn)
    converted_inputs = convert_inputs(job.inputs, annotations)

    logger.info(job.inputs)

    async def event_generator():
        async for point in run_analysis(analysis_fn, converted_inputs):
            # SSE format
            yield (f"event: update\ndata: {json.dumps(point)}\n\n")

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
