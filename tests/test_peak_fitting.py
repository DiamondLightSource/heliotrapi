import numpy as np
import pytest

from heliotrapi.analyses.peak_fitting import gaussian, gaussian_fit


def test_gaussian_function():
    x = np.array([0.0, 1.0, 2.0])
    y = gaussian(x, amplitude=2.0, x0=1.0, sigma=1.0)
    assert isinstance(y, np.ndarray)
    assert np.isclose(y[1], 2.0)


@pytest.mark.asyncio
async def test_gaussian_fit_invalid_data_returns_error():
    result = gaussian_fit([1], [1])  # noqs
    assert isinstance(result, dict)
    assert "error" in result
