import asyncio
from typing import cast

import pytest
from xrpd_toolbox.utils.messenger import Messenger

from heliotrapi.models import AnalysisRequest
from heliotrapi.task_queue import QueueManager
from heliotrapi.task_queue.manager import validate_inputs


@pytest.mark.asyncio
async def test_queue_manager_worker_success(monkeypatch):
    queue_manager = QueueManager(workers=1)

    async def fake_analysis(number):
        return number * 2

    monkeypatch.setattr(
        "heliotrapi.analysis_core.registry.get_analysis", lambda name: fake_analysis
    )

    job = AnalysisRequest(analysis_name="double", inputs={"number": 2})
    await queue_manager.enqueue(job)

    worker_task = asyncio.create_task(queue_manager.worker())
    await asyncio.wait_for(queue_manager.queue.join(), timeout=1.0)

    assert job.request_id in queue_manager.results
    assert queue_manager.latest_result is not None
    assert queue_manager.latest_result.analysis_name == "double"

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task


@pytest.mark.asyncio
async def test_queue_manager_enqueue_success_sends_message(monkeypatch):
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

    async def fake_analysis(number):
        return number * 2

    monkeypatch.setattr(
        "heliotrapi.analysis_core.registry.get_analysis", lambda name: fake_analysis
    )

    job = AnalysisRequest(analysis_name="double", inputs={"number": 2})
    response = await queue_manager.enqueue(job)

    assert response.accepted is True
    assert messenger.sent


def test_validate_inputs_missing_required_parameter():
    def analysis(x: int, y: int = 1):
        return x + y

    with pytest.raises(ValueError, match="Missing required parameter: x"):
        validate_inputs(analysis, {"y": 2})


def test_validate_inputs_invalid_value_type():
    def analysis(x: int):
        return x

    with pytest.raises(ValueError, match="Invalid value for 'x'"):
        validate_inputs(analysis, {"x": "not-an-int"})


def test_validate_inputs_unknown_extra_parameter():
    def analysis(x: int):
        return x

    with pytest.raises(ValueError, match="Unknown parameters"):
        validate_inputs(analysis, {"x": 1, "extra": 2})


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

    async def failing_analysis():
        raise KeyError("missing")

    monkeypatch.setattr(
        "heliotrapi.analysis_core.registry.get_analysis",
        lambda name: failing_analysis,
    )

    job = AnalysisRequest(analysis_name="missing", inputs={})
    await queue_manager.enqueue(job)

    worker_task = asyncio.create_task(queue_manager.worker())
    await asyncio.wait_for(queue_manager.queue.join(), timeout=1.0)
    assert job.request_id in queue_manager.results
    assert queue_manager.latest_result is not None
    assert queue_manager.latest_result.status == "failed"
    assert messenger.sent

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task


@pytest.mark.asyncio
async def test_queue_manager_enqueue_failure_sets_latest_result_and_sends_message(
    monkeypatch,
):
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
        "heliotrapi.analysis_core.registry.get_analysis",
        lambda name: (_ for _ in ()).throw(KeyError("missing")),
    )

    job = AnalysisRequest(analysis_name="missing", inputs={})
    response = await queue_manager.enqueue(job)

    assert response.accepted is False
    assert queue_manager.latest_result is not None
    assert queue_manager.latest_result.status == "failed"
    assert messenger.sent
    assert job.request_id in queue_manager.results
