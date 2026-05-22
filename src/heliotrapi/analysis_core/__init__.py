import importlib

from indigoapi.config import Config

from .decorator import analysis
from .loader import get_async_function, load_analyses, load_plugins
from .registry import (
    ANALYSIS_REGISTRY,
    AnalysisNotFoundError,
    get_analysis,
    list_analyses,
    register_analysis,
)

MODULE_NAMES: list[str] = []


def initialize_analyses(register_all: bool = False):
    """Load built-in analyses and user plugins. Call during server startup."""
    global MODULE_NAMES

    package = importlib.import_module("indigoapi.analyses")
    MODULE_NAMES = load_analyses(package)

    config = Config.load_config()
    load_plugins(config, register_all=register_all)


__all__ = [
    "analysis",
    "get_async_function",
    "load_analyses",
    "load_plugins",
    "ANALYSIS_REGISTRY",
    "AnalysisNotFoundError",
    "get_analysis",
    "list_analyses",
    "register_analysis",
    "initialize_analyses",
    "MODULE_NAMES",
]
