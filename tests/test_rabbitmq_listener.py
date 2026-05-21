import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from indigoapi.models import AnalysisRequest
from indigoapi.task_queue import QueueManager
from indigoapi.task_queue.rabbitmq import _StompListener


@pytest.mark.filterwarnings("ignore::ResourceWarning")
def test_stomp_listener_message_routes_enqueue(monkeypatch):
    enqueued = {}

    def fake_enqueue(job):
        enqueued["job"] = job

    queue_manager = cast(QueueManager, SimpleNamespace(enqueue=fake_enqueue))
    loop = asyncio.new_event_loop()

    try:
        listener = _StompListener(queue_manager, loop)  # type: ignore

        def fake_run_coro_threadsafe(coro, event_loop):
            return None

        monkeypatch.setattr(
            "indigoapi.task_queue.rabbitmq.asyncio.run_coroutine_threadsafe",
            fake_run_coro_threadsafe,
        )

        frame = SimpleNamespace(
            body=json.dumps(
                {
                    "analysis_name": "double",
                    "inputs": {"number": 2},
                }
            )
        )
        listener.on_message(frame)
        assert "job" in enqueued
    finally:
        loop.close()


@pytest.mark.filterwarnings("ignore::ResourceWarning")
def test_stomp_listener_invalid_json(monkeypatch):
    loop = asyncio.new_event_loop()
    try:
        queue_manager = cast(QueueManager, SimpleNamespace(enqueue=Mock()))
        listener = _StompListener(queue_manager, loop)  # type: ignore

        monkeypatch.setattr(
            "indigoapi.task_queue.rabbitmq.asyncio.run_coroutine_threadsafe",
            lambda coro, event_loop: None,
        )
        frame = SimpleNamespace(body="not-a-json")
        listener.on_message(frame)
    finally:
        loop.close()


@pytest.mark.filterwarnings("ignore::ResourceWarning")
def test_stomp_listener_connection_events():
    loop = asyncio.new_event_loop()
    try:
        queue_manager = cast(QueueManager, SimpleNamespace(enqueue=Mock()))
        listener = _StompListener(queue_manager, loop)  # type: ignore

        listener.on_connected(None)
        listener.on_disconnected()
        listener.on_error(SimpleNamespace(body="error"))
    finally:
        loop.close()


def test_parse_job_direct_analysis():
    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    data = {"analysis_name": "double", "inputs": {"number": 2}}
    job = listener.parse_job(data)

    assert isinstance(job, AnalysisRequest)
    assert job.analysis_name == "double"


def test_parse_job_data_event_ignored():
    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    job = listener.parse_job({"event_type": "foo", "task_id": "123"})
    assert job is None


def test_parse_job_scan_message_ignored():
    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    data = {
        "status": "ok",
        "filePath": "/tmp/file",
        "visitDirectory": "/tmp",
        "swmrStatus": "open",
        "scanNumber": 1,
        "scanDimensions": [1],
        "percentageComplete": 100.0,
    }
    job = listener.parse_job(data)
    assert job is None


def test_parse_job_worker_event_complete():
    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    data = {"state": "running", "task_status": {"task_complete": True}}
    job = listener.parse_job(data)
    assert isinstance(job, AnalysisRequest)


def test_on_message_logs_failure(monkeypatch):
    loop = asyncio.new_event_loop()
    listener = _StompListener(
        queue_manager=cast(QueueManager, SimpleNamespace(enqueue=Mock())),
        loop=loop,
    )

    class BadFrame:
        body = "not-json"

    recorded = []

    def fake_error(msg):
        recorded.append(msg)

    monkeypatch.setattr("indigoapi.task_queue.rabbitmq.logger.error", fake_error)
    listener.on_message(BadFrame())

    assert recorded
