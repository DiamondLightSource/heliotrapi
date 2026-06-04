from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.registry import register_analysis

P = ParamSpec("P")
R = TypeVar("R")


def analysis(
    name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, Awaitable[R]]]:
    """Decorator to register a function as an analysis.
    Converts sync functions to async."""

    def decorator(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
        async_fn = make_function_async(func)
        name_to_register = name or func.__name__

        register_analysis(name_to_register, async_fn)
        return async_fn

    return decorator
