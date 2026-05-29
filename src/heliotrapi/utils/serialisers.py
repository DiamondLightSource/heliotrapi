"""Utilities for serializing and converting data types."""

import inspect
import json
from typing import Any, Union, get_args, get_origin

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


def _parse_list_string(value: str) -> list:
    """Parse a comma-separated or JSON array string into a list."""
    s = value.strip()
    if s.startswith("["):
        return json.loads(s)
    return [v.strip() for v in s.split(",") if v.strip()]


def _infer(value: Any) -> Any:
    """Best-effort type inference when no annotation is available."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    for literal, result in (
        ("true", True),
        ("false", False),
        ("none", None),
        ("null", None),
    ):
        if s.lower() == literal:
            return result
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    if s.startswith(("[", "{")):
        try:
            return json.loads(s)
        except (ValueError, json.JSONDecodeError):
            pass
    return value


def deserialise(value: Any, annotation: Any) -> Any:
    """
    Convert a JSON-deserialised value into the expected Python type using the
    parameter annotation. Falls back to value introspection when the annotation
    is absent or too broad (e.g. bare strings, numeric strings, list-like values).
    """
    if annotation is inspect.Parameter.empty:
        return _infer(value)

    # Allow None only where the annotation permits it
    if value is None:
        if type(None) in get_args(annotation) or annotation is type(None):
            return None
        raise ValueError(
            f"Received null for non-optional parameter (annotation: {annotation})"
        )

    # Unwrap Optional[X] / X | None → recurse with the inner type
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        return deserialise(value, non_none[0]) if len(non_none) == 1 else _infer(value)

    ann_str = str(annotation).lower()

    if annotation is np.ndarray or "ndarray" in ann_str or "numpy" in ann_str:
        if isinstance(value, str):
            value = _parse_list_string(value)
        elif isinstance(value, (int, float)):
            value = [value]
        return np.array(value, dtype=float)

    if annotation is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes"):
                return True
            if s in ("false", "0", "no"):
                return False
        raise ValueError(f"Cannot convert {value!r} to bool")

    if annotation is int:
        if isinstance(value, bool):
            raise ValueError(f"Cannot convert {value!r} to int")
        if isinstance(value, (int, float)) and (
            not isinstance(value, float) or value.is_integer()
        ):
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        raise ValueError(f"Cannot convert {value!r} to int")

    if annotation is float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                pass
        raise ValueError(f"Cannot convert {value!r} to float")

    if annotation is str:
        return str(value)

    origin = get_origin(annotation)

    if origin is list:
        item_type = get_args(annotation)[0]
        if isinstance(value, str):
            value = _parse_list_string(value)
        elif not isinstance(value, (list, tuple)):
            value = [value]
        return [deserialise(v, item_type) for v in value]

    if origin is tuple:
        if isinstance(value, str):
            value = json.loads(value.strip())
        return tuple(
            deserialise(v, t) for v, t in zip(value, get_args(annotation), strict=True)
        )

    if origin is dict:
        key_type, val_type = get_args(annotation)
        if isinstance(value, str):
            value = json.loads(value.strip())
        return {
            deserialise(k, key_type): deserialise(v, val_type) for k, v in value.items()
        }

    return _infer(value) if isinstance(value, str) else value
