import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

from heliotrapi.models import AnalysisResult
from heliotrapi.task_queue import QueueManager, cleanup_results


def make_result(request_id: uuid.UUID, finished_at: datetime) -> AnalysisResult:
    return AnalysisResult(
        request_id=request_id,
        analysis_name="double",
        status="completed",
        result=10,
        created_at=finished_at,
        finished_at=finished_at,
    )


async def run_cleanup_once(queue_manager, ttl, monkeypatch):
    async def fake_sleep(interval):
        raise asyncio.CancelledError

    monkeypatch.setattr("heliotrapi.task_queue.cleanup.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await cleanup_results(queue_manager, ttl=ttl, interval=0)


@pytest.mark.asyncio
async def test_cleanup_results_removes_expired(monkeypatch):
    qm = QueueManager()
    request_id = uuid.uuid4()
    qm.results[request_id] = make_result(
        request_id, datetime.now() - timedelta(seconds=10)
    )

    await run_cleanup_once(qm, ttl=1, monkeypatch=monkeypatch)

    assert len(qm.results) == 0


@pytest.mark.asyncio
async def test_cleanup_results_keeps_fresh(monkeypatch):
    qm = QueueManager()
    request_id = uuid.uuid4()
    qm.results[request_id] = make_result(request_id, datetime.now())

    await run_cleanup_once(qm, ttl=60, monkeypatch=monkeypatch)

    assert len(qm.results) == 1
