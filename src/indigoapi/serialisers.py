"""Utilities for serializing and converting data types."""

from typing import Any

import numpy as np


def serialise(result: Any) -> Any:
    """
    Convert numpy and other non-JSON-serializable types to native Python types.

    Recursively handles:
    - numpy scalars (int64, float64, etc.) → Python int/float
    - numpy arrays → Python lists
    - numpy bool → Python bool
    - Nested structures (lists, dicts, tuples)

    Args:
        result: The result value to serialize

    Returns:
        A JSON-serializable version of the result
    """
    if result is None:
        return None

    # Handle numpy types
    if isinstance(result, np.ndarray):
        return result.tolist()
    elif isinstance(result, (np.integer, np.floating)):
        return result.item()
    elif isinstance(result, np.bool_):
        return bool(result)
    elif isinstance(result, np.complexfloating):
        return complex(result)

    # Handle Python collections recursively
    elif isinstance(result, dict):
        return {key: serialise(value) for key, value in result.items()}
    elif isinstance(result, (list, tuple)):
        return [serialise(item) for item in result]
    elif isinstance(result, set):
        return [serialise(item) for item in result]

    # Return other types as-is
    return result
