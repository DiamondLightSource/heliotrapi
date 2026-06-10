import asyncio
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest

from heliotrapi.models import AnalysisRequest, AnalysisResult
from heliotrapi.task_queue.manager import QueueManager, validate_inputs
from heliotrapi.utils.messenger import Messenger


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


@pytest.mark.asyncio
async def test_worker_catches_exception_and_marks_job_failed():
    async def failing_analysis(**kwargs):
        raise RuntimeError("analysis exploded")

    job = AnalysisRequest(
        request_id=uuid4(),
        analysis_name="test_analysis",
        inputs={},
    )

    qm = QueueManager()

    qm.results[job.request_id] = AnalysisResult(
        request_id=job.request_id,
        analysis_name=job.analysis_name,
        inputs=job.inputs,
        status="running",
        result=None,
        created_at=job.created_at,
        finished_at=None,
    )

    await qm.queue.put(job)

    with patch(
        "heliotrapi.task_queue.manager.get_analysis",
        return_value=failing_analysis,
    ):
        worker_task = asyncio.create_task(qm.worker())

        await qm.queue.join()

        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task

    result = qm.results[job.request_id]

    assert result.status == "failed"
    assert "analysis exploded" in result.result
    assert qm.latest_result == result


@pytest.mark.asyncio
async def test_worker_sends_slack_message_on_failure():
    async def failing_analysis(**kwargs):
        raise RuntimeError("analysis exploded")

    job = AnalysisRequest(
        request_id=uuid4(),
        analysis_name="test_analysis",
        inputs={},
    )

    qm = QueueManager(slack_webhook_url="https://slack.example.com")

    qm.results[job.request_id] = AnalysisResult(
        request_id=job.request_id,
        analysis_name=job.analysis_name,
        inputs=job.inputs,
        status="running",
        result=None,
        created_at=job.created_at,
        finished_at=None,
    )

    await qm.queue.put(job)

    with (
        patch(
            "heliotrapi.task_queue.manager.get_analysis",
            return_value=failing_analysis,
        ),
        patch("heliotrapi.task_queue.manager.send_slack_failure") as mock_slack,
    ):
        worker_task = asyncio.create_task(qm.worker())

        await qm.queue.join()

        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task

    mock_slack.assert_called_once()

    _, kwargs = mock_slack.call_args

    assert kwargs["webhook_url"] == "https://slack.example.com"
    assert "analysis exploded" in kwargs["message"]


def test_enqueue_sends_slack_on_failure():

    job = AnalysisRequest(
        request_id=uuid4(),
        analysis_name="NON_EXISTENT_ANALYSIS",
        inputs={"x": "bad"},
    )

    qm = QueueManager(slack_webhook_url="https://slack.example.com")

    with (
        patch(
            "heliotrapi.task_queue.manager.get_analysis",
            side_effect=Exception("boom"),
        ),
        patch("heliotrapi.task_queue.manager.send_slack_failure") as mock_slack,
    ):
        import asyncio

        asyncio.run(qm.enqueue(job))

    mock_slack.assert_called_once()

    _, kwargs = mock_slack.call_args
    assert "boom" in kwargs["message"]
