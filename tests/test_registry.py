import pytest

from heliotrapi.analysis_core.registry import (
    ANALYSIS_REGISTRY,
    register_analysis,
)


def test_registry_register_duplicate_raises():
    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        register_analysis("duplicate_test", lambda x: x)
        with pytest.raises(ValueError):
            register_analysis("duplicate_test", lambda x: x)
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
