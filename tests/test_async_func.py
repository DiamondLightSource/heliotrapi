import asyncio
import threading

import pytest

from heliotrapi.analysis_core.async_func import (
    CURRENT_CANCELLER,
    AnalysisCancelledError,
    ThreadCanceller,
    make_function_async,
)


def test_canceller_start_after_cancel_raises():
    canceller = ThreadCanceller()
    canceller.cancel()

    with pytest.raises(AnalysisCancelledError):
        canceller.start()


def test_canceller_tracks_thread_until_finish():
    canceller = ThreadCanceller()

    canceller.start()
    assert canceller.thread_id == threading.get_ident()

    canceller.finish()
    assert canceller.thread_id is None


def test_canceller_cancel_when_not_running_raises_nothing():
    canceller = ThreadCanceller()
    canceller.cancel()  # no thread registered, so nothing is raised anywhere

    assert canceller.cancelled


@pytest.mark.asyncio
async def test_sync_function_runs_without_canceller():
    # e.g. streaming, which doesn't go through the queue worker
    assert CURRENT_CANCELLER.get() is None

    async_fn = make_function_async(lambda x: x * 2)

    assert await async_fn(21) == 42


@pytest.mark.asyncio
async def test_sync_function_registers_and_clears_its_thread():
    canceller = ThreadCanceller()
    seen = {}

    def analysis():
        seen["thread_id"] = canceller.thread_id
        seen["ident"] = threading.get_ident()
        return 1

    CURRENT_CANCELLER.set(canceller)
    assert await make_function_async(analysis)() == 1

    assert seen["thread_id"] == seen["ident"]
    assert canceller.thread_id is None


@pytest.mark.asyncio
async def test_sync_function_cancelled_before_start_never_runs():
    canceller = ThreadCanceller()
    canceller.cancel()
    calls = []

    CURRENT_CANCELLER.set(canceller)
    with pytest.raises(AnalysisCancelledError):
        await make_function_async(lambda: calls.append(1))()

    assert not calls


@pytest.mark.asyncio
async def test_sync_function_cancelled_while_running_raises_in_thread():
    canceller = ThreadCanceller()
    started = threading.Event()

    def busy():
        started.set()
        while True:
            pass

    CURRENT_CANCELLER.set(canceller)
    task = asyncio.ensure_future(make_function_async(busy)())
    assert await asyncio.to_thread(started.wait, 1.0)

    canceller.cancel()

    with pytest.raises(AnalysisCancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    assert canceller.thread_id is None
