import asyncio
import ctypes
import inspect
import threading
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class AnalysisCancelledError(Exception):
    """Raised inside a sync analysis's thread when its job is cancelled"""


class ThreadCanceller:
    """Lets a job cancel the sync analysis running in its thread.

    Python can't kill a thread, but CPython can raise an exception in one.
    It lands at the next Python bytecode, so a single long C call (a big numpy
    operation, time.sleep) isn't interrupted until it returns.

    Threads are reused by the pool, so the exception is only raised while the
    analysis is running - the lock stops it leaking into the next job.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.thread_id: int | None = None
        self.cancelled = False

    def start(self) -> None:
        """Called in the analysis thread before the analysis runs"""
        with self.lock:
            if self.cancelled:
                raise AnalysisCancelledError
            self.thread_id = threading.get_ident()

    def finish(self) -> None:
        """Called in the analysis thread once the analysis returns"""
        with self.lock:
            self.thread_id = None

    def cancel(self) -> None:
        with self.lock:
            self.cancelled = True
            if self.thread_id is not None:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(self.thread_id),
                    ctypes.py_object(AnalysisCancelledError),
                )


# set by the queue worker for each job, so the sync wrapper can find its canceller
CURRENT_CANCELLER: ContextVar[ThreadCanceller | None] = ContextVar(
    "CURRENT_CANCELLER", default=None
)


def make_function_async(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    if inspect.iscoroutinefunction(func):
        return func  # type: ignore[return-value]

    @wraps(func)
    async def async_fn(*args: P.args, **kwargs: P.kwargs) -> R:
        canceller = CURRENT_CANCELLER.get()

        # not run by the queue worker (e.g. streaming), so nothing can cancel it
        if canceller is None:
            return await asyncio.to_thread(func, *args, **kwargs)

        def run() -> R:
            canceller.start()
            try:
                return func(*args, **kwargs)
            finally:
                canceller.finish()

        return await asyncio.to_thread(run)

    return async_fn
