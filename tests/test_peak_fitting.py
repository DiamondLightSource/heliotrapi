import numpy as np
import pytest

from indigoapi.analyses.peak_fitting import gaussian, gaussian_fit


def test_gaussian_function():
    x = np.array([0.0, 1.0, 2.0])
    y = gaussian(x, amplitude=2.0, x0=1.0, sigma=1.0)
    assert np.isclose(y[1], 2.0)


@pytest.mark.asyncio
async def test_gaussian_fit_invalid_data_returns_error():
    result = await gaussian_fit([1], [1])
    assert isinstance(result, dict)
    assert "error" in result
