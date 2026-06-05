import asyncio
import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def make_function_async(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    if inspect.iscoroutinefunction(func):
        return func  # type: ignore[return-value]

    @wraps(func)
    async def async_fn(*args: P.args, **kwargs: P.kwargs) -> R:
        return await asyncio.to_thread(func, *args, **kwargs)

    return async_fn
