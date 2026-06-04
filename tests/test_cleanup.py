import asyncio
import time
import uuid
from datetime import datetime

import pytest

from heliotrapi.task_queue import cleanup_results
from heliotrapi.task_queue.cleanup import _extract_timestamp


@pytest.mark.asyncio
async def test_cleanup_results_removes_expired(monkeypatch):
    class FakeQueue:
        pass

    now = time.time() - 10
    fake_queue = FakeQueue()
    fake_queue.results = {uuid.uuid4(): (None, now)}  # type: ignore

    async def fake_sleep(interval):
        raise asyncio.CancelledError

    monkeypatch.setattr("heliotrapi.task_queue.cleanup.asyncio.sleep", fake_sleep)

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

    monkeypatch.setattr("heliotrapi.task_queue.cleanup.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await cleanup_results(fake_queue, ttl=60, interval=0)

    assert len(fake_queue.results) == 1  # type: ignore


@pytest.mark.parametrize(
    "input_dict,expected_fn",
    [
        # numeric finished_at
        ({"finished_at": 123.0}, lambda dt: 123.0),
        # datetime finished_at
        ({"finished_at": datetime(2024, 1, 1)}, lambda dt: dt.timestamp()),
        # created_at fallback
        ({"created_at": datetime(2024, 1, 1)}, lambda dt: dt.timestamp()),
        # bad timestamp object → None
        ({"finished_at": object()}, lambda dt: None),
    ],
)
def test_extract_timestamp_dict_cases(input_dict, expected_fn):
    dt = datetime(2024, 1, 1)

    assert _extract_timestamp(input_dict) == expected_fn(dt)


@pytest.mark.parametrize(
    "value,expected",
    [
        (12345, None),
        ("not-a-supported-type", None),
        (None, None),
    ],
)
def test_extract_timestamp_fallback(value, expected):
    assert _extract_timestamp(value) == expected


class BadTimestamp:
    def timestamp(self):
        raise RuntimeError("fail")
