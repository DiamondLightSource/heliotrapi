import inspect

import numpy as np

from indigoapi.utils.serialisers import deserialise, serialise


def test_serialise_numpy_scalars_and_nested_collections():
    result = serialise(
        {
            "x": np.array([1, 2]),
            "n": np.int64(5),
            "f": np.float32(1.5),
            "flag": np.bool_(True),
            "c": np.complex128(1 + 2j),
            "nested": {"value": np.int16(3), "tuple": (np.int32(4),)},
            "set_data": {1, 2},
        }
    )

    assert result["x"] == [1, 2]
    assert result["n"] == 5
    assert result["f"] == 1.5
    assert result["flag"] is True
    assert result["c"] == 1 + 2j
    assert result["nested"]["value"] == 3
    assert result["nested"]["tuple"] == [4]
    assert sorted(result["set_data"]) == [1, 2]


def test_deserialise_native_annotations_and_nested_types():
    assert deserialise("1", int) == 1
    assert deserialise("1.5", float) == 1.5
    assert deserialise(1, bool) is True
    assert deserialise(1, str) == "1"

    array = deserialise([1, 2, 3], np.ndarray)
    assert isinstance(array, np.ndarray)
    assert array.tolist() == [1.0, 2.0, 3.0]

    assert deserialise(["1", "2"], list[int]) == [1, 2]
    assert deserialise(("1", 2), tuple[str, int]) == ("1", 2)
    assert deserialise({"a": "1"}, dict[str, int]) == {"a": 1}


def test_deserialise_no_annotation_returns_original_value():
    value = {"x": 1}
    assert deserialise(value, inspect.Parameter.empty) == value
