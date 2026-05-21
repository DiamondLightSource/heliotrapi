import asyncio
from types import SimpleNamespace

import pytest

from indigoapi.analyses.decorator import analysis
from indigoapi.analyses.registry import (
    ANALYSIS_REGISTRY,
    get_analysis,
    register_analysis,
)


def test_analysis_decorator_registers_sync_function():
    original_registry = ANALYSIS_REGISTRY.copy()
    try:

        @analysis("my_test_double")
        def my_double(number: int) -> int:
            return number * 2

        assert asyncio.iscoroutinefunction(my_double)
        fn = get_analysis("my_test_double")
        result = asyncio.run(fn(3))
        assert result == 6
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)


def test_registry_register_duplicate_raises():
    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        register_analysis("duplicate_test", lambda x: x)
        with pytest.raises(ValueError):
            register_analysis("duplicate_test", lambda x: x)
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)


def test_registry_imports_missing_module(monkeypatch):
    original_registry = ANALYSIS_REGISTRY.copy()
    if "double" in ANALYSIS_REGISTRY:
        del ANALYSIS_REGISTRY["double"]

    def fake_import(module_name):
        return SimpleNamespace(double=lambda x: x * 2)

    monkeypatch.setattr(
        "indigoapi.analyses.registry.importlib.import_module",
        fake_import,
    )

    try:
        fn = get_analysis("double")
        assert callable(fn)
        assert fn(3) == 6
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
