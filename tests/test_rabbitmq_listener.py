import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from indigoapi.rabbitmq_listener import _StompListener


@pytest.mark.filterwarnings("ignore::ResourceWarning")
def test_stomp_listener_message_routes_enqueue(monkeypatch):
    enqueued = {}

    def fake_enqueue(job):
        enqueued["job"] = job

    queue_manager = SimpleNamespace(enqueue=fake_enqueue)
    loop = asyncio.new_event_loop()

    try:
        listener = _StompListener(queue_manager, loop)  # type: ignore

        def fake_run_coro_threadsafe(coro, event_loop):
            return None

        monkeypatch.setattr(
            "indigoapi.rabbitmq_listener.asyncio.run_coroutine_threadsafe",
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
        queue_manager = SimpleNamespace(enqueue=Mock())
        listener = _StompListener(queue_manager, loop)  # type: ignore

        monkeypatch.setattr(
            "indigoapi.rabbitmq_listener.asyncio.run_coroutine_threadsafe",
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
        queue_manager = SimpleNamespace(enqueue=Mock())
        listener = _StompListener(queue_manager, loop)  # type: ignore

        listener.on_connected(None)
        listener.on_disconnected()
        listener.on_error(SimpleNamespace(body="error"))
    finally:
        loop.close()
