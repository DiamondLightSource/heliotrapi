import inspect
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute

from indigoapi.analyses.registry import get_analysis, list_analyses
from indigoapi.models import AnalysisRequest, AnalysisResult
from indigoapi.queue_manager import QueueManager

ROUTER = APIRouter()

HEALTH_ROUTE = "/health"
ANALYSES_ROUTE = "/get_analyses"
ANALYSE_ROUTE = "/analyse"
RESULT_LATEST_ROUTE = "/result/latest"
RESULT_BY_ID_ROUTE = "/result/id/{request_id}"
ENDPOINTS_ROUTE = "/endpoints"


@ROUTER.get(HEALTH_ROUTE)
async def health():
    return {"status": "ok"}


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
                    "annotation": str(p.annotation)
                    if p.annotation != inspect.Parameter.empty
                    else "Any",
                }
            )
        return_annotation = (
            str(sig.return_annotation)
            if sig.return_annotation != inspect.Signature.empty
            else "Any"
        )
        analyses_info.append(
            {
                "name": name,
                "parameters": params,
                "return_annotation": return_annotation,
            }
        )
    return analyses_info


@ROUTER.post(ANALYSE_ROUTE)
async def analyse(request: Request, job: AnalysisRequest):
    queue: QueueManager = request.app.state.queue_manager
    await queue.enqueue(job)
    return {"request_id": job.request_id}


@ROUTER.get(RESULT_LATEST_ROUTE, response_model=AnalysisResult)
async def get_latest_result(request: Request):

    queue_manager = request.app.state.queue_manager

    if queue_manager.latest_result is None:
        raise HTTPException(status_code=404, detail="No results yet")

    return queue_manager.latest_result


@ROUTER.get(RESULT_BY_ID_ROUTE)
async def result(request: Request, request_id: UUID):
    queue: QueueManager = request.app.state.queue_manager
    if request_id not in queue.results:
        raise HTTPException(404, "Result not found")
    result, duration = queue.results[request_id]
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
