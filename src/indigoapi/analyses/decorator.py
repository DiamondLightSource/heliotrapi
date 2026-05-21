from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from indigoapi.analyses.loader import get_async_function
from indigoapi.analyses.registry import register_analysis

P = ParamSpec("P")
R = TypeVar("R")


def analysis(
    name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, Awaitable[R]]]:
    """Decorator to register a function as an analysis.
    Converts sync functions to async."""

    def decorator(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
        async_fn = get_async_function(func)
        name_to_register = name or func.__name__

        register_analysis(name_to_register, async_fn)
        return async_fn

    return decorator
