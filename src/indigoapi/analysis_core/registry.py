import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AnalysisNotFoundError(Exception):
    """Raised when a requested analysis cannot be found or imported."""


ANALYSIS_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_analysis(name: str, fn: Callable) -> None:
    if name in ANALYSIS_REGISTRY:
        raise ValueError(f"Analysis '{name}' already registered")
    ANALYSIS_REGISTRY[name] = fn
    logger.info(f"Registered analysis: {name}")


def list_analyses() -> list[str]:
    return list(ANALYSIS_REGISTRY.keys())


def get_analysis(name: str) -> Callable:
    if name not in ANALYSIS_REGISTRY:
        msg = f"Unknown analysis '{name}': analysis not found"
        raise AnalysisNotFoundError(msg)

    return ANALYSIS_REGISTRY[name]
