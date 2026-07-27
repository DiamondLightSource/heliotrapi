import asyncio
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest

from heliotrapi.models import AnalysisRequest
from heliotrapi.task_queue.manager import QueueManager, validate_inputs
from heliotrapi.utils.messenger import Messenger


class FakeMessenger:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def is_connected(self) -> bool:
        return True

    def send_message(self, destination: str, message: str) -> None:
        self.sent.append((destination, message))


@pytest.mark.asyncio
async def test_queue_manager_worker_success(fake_redis_client):
    queue_manager = QueueManager(redis_client=fake_redis_client, workers=1)

    job = AnalysisRequest(analysis_name="double", inputs={"number": 2})
    await queue_manager.enqueue(job)

    result = await queue_manager._process_job(job)

    assert result.analysis_name == "double"
    assert result.result == 4

    stored = await queue_manager.get_result(job.request_id)
    assert stored is not None
    assert stored.status == "completed"

    latest = await queue_manager.get_latest_result()
    assert latest is not None
    assert latest.analysis_name == "double"


@pytest.mark.asyncio
async def test_queue_manager_enqueue_success_sends_message(fake_redis_client):

    messenger = FakeMessenger()
    queue_manager = QueueManager(
        redis_client=fake_redis_client,
        workers=1,
        messenger=cast(Messenger, messenger),
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
async def test_queue_manager_worker_failure_sends_message(fake_redis_client):

    messenger = FakeMessenger()
    queue_manager = QueueManager(
        redis_client=fake_redis_client,
        workers=1,
        messenger=cast(Messenger, messenger),
    )

    async def failing_analysis(**kwargs):
        raise KeyError("missing")

    job = AnalysisRequest(analysis_name="missing", inputs={})

    with patch(
        "heliotrapi.task_queue.manager.get_analysis",
        return_value=failing_analysis,
    ):
        result = await queue_manager._process_job(job)

    assert result.status == "failed"
    assert messenger.sent


@pytest.mark.asyncio
async def test_queue_manager_enqueue_failure_sets_latest_result_and_sends_message(
    fake_redis_client,
):

    messenger = FakeMessenger()
    queue_manager = QueueManager(
        redis_client=fake_redis_client,
        workers=1,
        messenger=cast(Messenger, messenger),
    )

    job = AnalysisRequest(analysis_name="missing", inputs={})

    with patch(
        "heliotrapi.task_queue.manager.get_analysis",
        side_effect=Exception("boom"),
    ):
        response = await queue_manager.enqueue(job)

    assert response.accepted is False

    latest = await queue_manager.get_latest_result()
    assert latest is not None
    assert latest.status == "failed"
    assert messenger.sent

    stored = await queue_manager.get_result(job.request_id)
    assert stored is not None


@pytest.mark.asyncio
async def test_worker_catches_exception_and_marks_job_failed(fake_redis_client):
    async def failing_analysis(**kwargs):
        raise RuntimeError("analysis exploded")

    job = AnalysisRequest(
        request_id=uuid4(),
        analysis_name="test_analysis",
        inputs={},
    )

    qm = QueueManager(redis_client=fake_redis_client)

    with patch(
        "heliotrapi.task_queue.manager.get_analysis",
        return_value=failing_analysis,
    ):
        result = await qm._process_job(job)

    assert result.status == "failed"
    assert "analysis exploded" in result.result

    latest = await qm.get_latest_result()
    assert latest == result


@pytest.mark.asyncio
async def test_worker_sends_slack_message_on_failure(fake_redis_client):
    async def failing_analysis(**kwargs):
        raise RuntimeError("analysis exploded")

    job = AnalysisRequest(
        request_id=uuid4(),
        analysis_name="test_analysis",
        inputs={},
    )

    qm = QueueManager(
        redis_client=fake_redis_client, slack_webhook_url="https://slack.example.com"
    )

    with (
        patch(
            "heliotrapi.task_queue.manager.get_analysis",
            return_value=failing_analysis,
        ),
        patch("heliotrapi.task_queue.manager.send_slack_failure") as mock_slack,
    ):
        await qm._process_job(job)

    mock_slack.assert_called_once()

    _, kwargs = mock_slack.call_args

    assert kwargs["webhook_url"] == "https://slack.example.com"
    assert "analysis exploded" in kwargs["message"]


@pytest.mark.asyncio
async def test_enqueue_sends_slack_on_failure(fake_redis_client):

    job = AnalysisRequest(
        request_id=uuid4(),
        analysis_name="NON_EXISTENT_ANALYSIS",
        inputs={"x": "bad"},
    )

    qm = QueueManager(
        redis_client=fake_redis_client, slack_webhook_url="https://slack.example.com"
    )

    with (
        patch(
            "heliotrapi.task_queue.manager.get_analysis",
            side_effect=Exception("boom"),
        ),
        patch("heliotrapi.task_queue.manager.send_slack_failure") as mock_slack,
    ):
        await qm.enqueue(job)

    mock_slack.assert_called_once()

    _, kwargs = mock_slack.call_args
    assert "boom" in kwargs["message"]


@pytest.mark.asyncio
async def test_queue_manager_worker_reads_from_queue(fake_redis_client):
    """A thin end-to-end check that worker() dequeues and processes a real
    job via BRPOP, separate from the _process_job unit tests above."""
    queue_manager = QueueManager(redis_client=fake_redis_client, workers=1)
    job = AnalysisRequest(analysis_name="double", inputs={"number": 3})
    await queue_manager.enqueue(job)

    worker_task = asyncio.create_task(queue_manager.worker())
    try:
        for _ in range(200):
            result = await queue_manager.get_result(job.request_id)
            if result is not None and result.status == "completed":
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("worker() never processed the enqueued job")
    finally:
        # Fire-and-forget cancel, matching server.py's own shutdown path -
        # fakeredis's blocking BRPOP spawns an internal task that doesn't
        # reliably respond to the awaiting task's cancellation in every
        # interleaving, so we don't assert on it finishing here.
        worker_task.cancel()

    assert result is not None
    assert result.result == 6
