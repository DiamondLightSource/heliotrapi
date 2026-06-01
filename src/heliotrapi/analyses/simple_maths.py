from collections.abc import Sequence

import numpy as np

from heliotrapi.analysis_core.decorator import analysis


@analysis()
def double(number: float | int) -> float:
    """Example analysis that doubles a number."""

    return number * 2


@analysis()
def sum_numbers(numbers: Sequence[float | int]) -> float:
    """Example analysis that sums a sequence of numbers."""

    return np.sum(numbers)


@analysis()
def sine_wave(array: np.ndarray | None) -> np.ndarray:
    """Example analysis that returns a sine wave for a given array,
    or a default sine wave 0->2pi if no array is provided."""
    if array is None:
        array = np.linspace(0, 2 * np.pi, 100)

    sine = np.sin(array)

    return sine
