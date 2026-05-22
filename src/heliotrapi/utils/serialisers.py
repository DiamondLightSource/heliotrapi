"""Utilities for serializing and converting data types."""

import inspect
from typing import Any, get_args, get_origin

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


def deserialise(value: Any, annotation: Any) -> Any:
    """
    Convert a JSON-deserialized value into the expected Python type
    based on a function parameter annotation.
    """

    if annotation is inspect.Parameter.empty:
        return value

    ann_str = str(annotation).lower()

    if annotation is np.ndarray or "ndarray" in ann_str or "numpy" in ann_str:
        return np.array(value, dtype=float)

    if annotation is int:
        return int(value)

    if annotation is float:
        return float(value)

    if annotation is bool:
        return bool(value)

    if annotation is str:
        return str(value)

    origin = get_origin(annotation)

    if origin is list:
        item_type = get_args(annotation)[0]

        return [deserialise(v, item_type) for v in value]

    if origin is tuple:
        item_types = get_args(annotation)

        return tuple(deserialise(v, t) for v, t in zip(value, item_types, strict=True))

    if origin is dict:
        key_type, val_type = get_args(annotation)

        return {
            deserialise(k, key_type): deserialise(v, val_type) for k, v in value.items()
        }

    return value
