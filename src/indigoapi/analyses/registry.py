import importlib
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

ANALYSIS_REGISTRY = {}


def register_analysis(name: str, fn: Callable) -> None:
    if name in ANALYSIS_REGISTRY:
        raise ValueError(f"Analysis '{name}' already registered")
    ANALYSIS_REGISTRY[name] = fn
    logger.info(f"Registered analysis: {name}")


def list_analyses() -> list[str]:

    return list(ANALYSIS_REGISTRY.keys())


def get_analysis(name: str) -> Callable:
    if name not in ANALYSIS_REGISTRY:
        try:
            mod = importlib.import_module(f"indigoapi.analyses.{name}")
            func = getattr(mod, name)
            ANALYSIS_REGISTRY[name] = func
        except Exception as e:
            print(f"Unknown analysis '{name}': {e}")
            print("Available analyses:")
            for analysis in list_analyses():
                print(analysis)

    return ANALYSIS_REGISTRY[name]
