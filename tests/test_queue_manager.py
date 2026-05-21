import asyncio
from typing import cast

import pytest
from xrpd_toolbox.utils.messenger import Messenger

from indigoapi.models import AnalysisRequest
from indigoapi.task_queue import QueueManager


async def wait_for_result(queue_manager, request_id, timeout=1.0):
    start = asyncio.get_running_loop().time()
    while True:
        if request_id in queue_manager.results:
            return
        if asyncio.get_running_loop().time() - start > timeout:
            raise TimeoutError()
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_queue_manager_worker_success(monkeypatch):
    queue_manager = QueueManager(workers=1)

    async def fake_analysis(number):
        return number * 2

    monkeypatch.setattr(
        "indigoapi.analysis_core.registry.get_analysis", lambda name: fake_analysis
    )

    job = AnalysisRequest(analysis_name="double", inputs={"number": 2})
    await queue_manager.enqueue(job)

    worker_task = asyncio.create_task(queue_manager.worker())
    await asyncio.wait_for(wait_for_result(queue_manager, job.request_id), timeout=1.0)

    assert job.request_id in queue_manager.results
    assert queue_manager.latest_result is not None
    assert queue_manager.latest_result.analysis_name == "double"

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task


@pytest.mark.asyncio
async def test_queue_manager_worker_failure_sends_message(monkeypatch):
    class FakeMessenger:
        def __init__(self):
            self.sent = []

        def send_message(self, destination, message):
            self.sent.append((destination, message))

    messenger = FakeMessenger()
    queue_manager = QueueManager(
        workers=1,
        messenger=cast(Messenger, messenger),
    )

    monkeypatch.setattr(
        "indigoapi.analysis_core.registry.get_analysis",
        lambda name: (_ for _ in ()).throw(KeyError("missing")),
    )

    job = AnalysisRequest(analysis_name="missing", inputs={})
    await queue_manager.enqueue(job)

    worker_task = asyncio.create_task(queue_manager.worker())
    await asyncio.wait_for(wait_for_result(queue_manager, job.request_id), timeout=1.0)

    assert job.request_id in queue_manager.results
    assert queue_manager.latest_result is not None
    assert queue_manager.latest_result.status == "failed"
    assert messenger.sent

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task
