import numpy as np
from scipy.optimize import curve_fit

from indigoapi.analysis_core.decorator import analysis


def gaussian(x: np.ndarray, amplitude: float, x0: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-((x - x0) ** 2) / (2 * sigma**2))


@analysis()
def gaussian_fit(x: list[int | float], y: list[int | float]):
    """
    data = {
        "x": [...],
        "y": [...]
    }
    returns: dict with keys "amplitude", "position", "width"
    """
    x = np.array(x)  # type: ignore
    y = np.array(y)  # type: ignore

    # initial guess: amplitude=max(y), position=argmax(y), width=std(x)
    a0 = np.max(y)
    x0 = x[np.argmax(y)]
    sigma0 = np.std(x)

    try:
        popt, _ = curve_fit(gaussian, x, y, p0=[a0, x0, sigma0])
        a, x0, sigma = popt
        return {"amplitude": float(a), "position": float(x0), "width": float(sigma)}
    except Exception as e:
        return {"error": str(e)}
