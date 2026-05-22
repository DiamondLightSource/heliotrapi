from collections.abc import Sequence

import numpy as np

from heliotrapi.analysis_core.decorator import analysis


@analysis()
def double(number: float | int) -> float:

    return number * 2


@analysis()
def sum_numbers(numbers: Sequence[float | int]) -> float:

    return np.sum(numbers)
