import asyncio
import inspect

import pytest

from heliotrapi.analysis_core.decorator import analysis
from heliotrapi.analysis_core.registry import (
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

        assert inspect.iscoroutinefunction(my_double)
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
