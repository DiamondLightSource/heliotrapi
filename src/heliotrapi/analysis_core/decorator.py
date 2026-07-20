from collections.abc import Callable
from inspect import signature
from typing import ParamSpec, TypeVar

from pydantic import BaseModel

from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.message_names import (
    FINISHED_NEXUS_ANALYSIS_NAME,
    START_MESSAGE_ANALYSIS_NAME,
    STARTED_NEXUS_ANALYSIS_NAME,
    STOP_MESSAGE_ANALYSIS_NAME,
    UPDATED_NEXUS_ANALYSIS_NAME,
)
from heliotrapi.analysis_core.registry import register_analysis
from heliotrapi.logger import logger
from heliotrapi.task_queue.message_models import (
    NexusMessage,
    StartMessage,
    StopMessage,
)

P = ParamSpec("P")
R = TypeVar("R")


def analysis(
    name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to register a function as an analysis.

    Registers an async-wrapped copy of *func* in the analysis registry (so the
    loader can call it uniformly), but returns *func* itself, completely
    unmodified. Importing the decorated function elsewhere therefore gives you
    back the original sync (or async) callable, with its original signature
    and return type.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name_to_register = name or func.__name__
        register_analysis(name_to_register, make_function_async(func))
        return func

    return decorator


def check_message_args(func: Callable, check_type: type[BaseModel]):
    """this function checks that the analysis that has been registered
    has only argument and that argument is called message and is of type BaseModel

    (When registering a function using one of the analysis decorators below)
    """

    sig = signature(func)

    params = list(sig.parameters.values())

    assert len(params) == 1, f"{func.__name__} must accept exactly one argument"

    param = params[0]

    assert param.name == "message", f"{func.__name__} argument must be named 'message'"

    annotation = param.annotation

    assert annotation is not param.empty, (
        f"{func.__name__} must type-annotate 'message'"
    )

    assert issubclass(annotation, check_type), (
        f"{func.__name__}.message must be a {check_type} subtype"
    )


def start_message_analysis(func: Callable[P, R]) -> Callable[P, R] | None:
    try:
        check_message_args(func, StartMessage)
        return analysis(START_MESSAGE_ANALYSIS_NAME)(func)
    except Exception as e:
        logger.error(
            f"{func.__name__} does not have proper arguments: {e}. "
            f"Nothing will happen on {FINISHED_NEXUS_ANALYSIS_NAME} "
        )
        return None


def stop_message_analysis(func: Callable[P, R]) -> Callable[P, R] | None:
    try:
        check_message_args(func, StopMessage)
        return analysis(STOP_MESSAGE_ANALYSIS_NAME)(func)
    except Exception as e:
        logger.error(
            f"{func.__name__} does not have proper arguments: {e}. "
            f"Nothing will happen on {STOP_MESSAGE_ANALYSIS_NAME} "
        )
        return None


def started_nexus_analysis(func: Callable[P, R]) -> Callable[P, R] | None:
    try:
        check_message_args(func, NexusMessage)
        return analysis(STARTED_NEXUS_ANALYSIS_NAME)(func)
    except Exception as e:
        logger.error(
            f"{func.__name__} does not have proper arguments: {e}. "
            f"Nothing will happen on {STARTED_NEXUS_ANALYSIS_NAME} "
        )
        return None


def updated_nexus_analysis(func: Callable[P, R]) -> Callable[P, R] | None:
    try:
        check_message_args(func, NexusMessage)
        return analysis(UPDATED_NEXUS_ANALYSIS_NAME)(func)
    except Exception as e:
        logger.error(
            f"{func.__name__} does not have proper arguments: {e}. "
            f"Nothing will happen on {UPDATED_NEXUS_ANALYSIS_NAME}"
        )


def finished_nexus_analysis(func: Callable[P, R]) -> Callable[P, R] | None:
    try:
        check_message_args(func, NexusMessage)
        return analysis(FINISHED_NEXUS_ANALYSIS_NAME)(func)
    except Exception as e:
        logger.error(
            f"{func.__name__} does not have proper arguments: {e}. "
            f"Nothing will happen on {FINISHED_NEXUS_ANALYSIS_NAME}"
        )
