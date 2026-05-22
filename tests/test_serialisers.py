import inspect

import numpy as np
import pytest

from indigoapi.utils.serialisers import deserialise, serialise


@pytest.mark.parametrize(
    "value, expected",
    [
        (np.int64(5), 5),
        (np.float32(1.5), 1.5),
        (np.bool_(True), True),
        (np.complex128(1 + 2j), 1 + 2j),
        (np.array([1, 2]), [1, 2]),
        (np.array([[1, 2], [3, 4]]), [[1, 2], [3, 4]]),
        ({1, 2}, [1, 2]),
        (None, None),
    ],
)
def test_serialise_numpy_scalars_and_collections(value, expected):
    result = serialise(value)

    if isinstance(value, set):
        assert sorted(result) == expected
    else:
        assert result == expected


@pytest.mark.parametrize(
    "value, annotation, expected",
    [
        ("1", int, 1),
        ("1.5", float, 1.5),
        (1, bool, True),
        (1, str, "1"),
        ([1, 2, 3], np.ndarray, np.array([1.0, 2.0, 3.0])),
        (["1", "2"], list[int], [1, 2]),
        (("1", 2), tuple[str, int], ("1", 2)),
        ({"a": "1"}, dict[str, int], {"a": 1}),
    ],
)
def test_deserialise_native_annotations_and_nested_types(value, annotation, expected):
    result = deserialise(value, annotation)

    if annotation is np.ndarray:
        assert isinstance(result, np.ndarray)
        assert result.tolist() == expected.tolist()
    else:
        assert result == expected


def test_deserialise_no_annotation_returns_original_value():
    value = {"x": 1}
    assert deserialise(value, inspect.Parameter.empty) == value
