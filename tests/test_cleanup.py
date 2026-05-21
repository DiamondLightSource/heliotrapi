import asyncio
import time
import uuid

import pytest

from indigoapi.queue import cleanup_results


@pytest.mark.asyncio
async def test_cleanup_results_removes_expired(monkeypatch):
    class FakeQueue:
        pass

    now = time.time() - 10
    fake_queue = FakeQueue()
    fake_queue.results = {uuid.uuid4(): (None, now)}  # type: ignore

    async def fake_sleep(interval):
        raise asyncio.CancelledError

    monkeypatch.setattr("indigoapi.queue.cleanup.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await cleanup_results(fake_queue, ttl=1, interval=0)

    assert fake_queue.results == {}  # type: ignore


@pytest.mark.asyncio
async def test_cleanup_results_keeps_fresh(monkeypatch):
    class FakeQueue:
        pass

    now = time.time()
    fake_queue = FakeQueue()
    fake_queue.results = {uuid.uuid4(): (None, now)}  # type: ignore

    async def fake_sleep(interval):
        raise asyncio.CancelledError

    monkeypatch.setattr("indigoapi.queue.cleanup.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await cleanup_results(fake_queue, ttl=60, interval=0)

    assert len(fake_queue.results) == 1  # type: ignore
