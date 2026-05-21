import numpy as np
import pytest

from indigoapi.analyses.peak_fitting import gaussian
from indigoapi.analysis_core.registry import (
    AnalysisNotFoundError,
    get_analysis,
    list_analyses,
)


@pytest.mark.asyncio
async def test_sync_plugin():

    fn = get_analysis("double")

    result = await fn(5)

    assert result == 10


@pytest.mark.asyncio
async def test_sum_numbers():

    print(list_analyses())

    fn = get_analysis("sum_numbers")

    result = await fn([5, 10])

    assert result == 15


@pytest.mark.asyncio
async def test_sync_plugin_zero():

    fn = get_analysis("double")

    result = await fn(0)

    assert result == 0


@pytest.mark.asyncio
async def test_sync_plugin_negative():

    fn = get_analysis("double")

    result = await fn(-3)

    assert result == -6


@pytest.mark.asyncio
async def test_async_with_gauss():

    fn = get_analysis("gaussian_fit")

    x = np.linspace(0, 10, 100)
    y = gaussian(x, 10, 5, 1)

    result = await fn(x, y)

    assert result["amplitude"] == 10.0


@pytest.mark.asyncio
async def test_invalid_analysis_name():

    with pytest.raises(AnalysisNotFoundError):
        get_analysis("nonexistent")
