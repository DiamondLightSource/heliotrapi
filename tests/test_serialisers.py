import inspect

import numpy as np
import pytest

from heliotrapi.utils.serialisers import deserialise, serialise


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


# =========================
# serialise() tests
# =========================


def test_serialise_none():
    assert serialise(None) is None


def test_serialise_numpy_array():
    arr = np.array([1, 2, 3])
    assert serialise(arr) == [1, 2, 3]


def test_serialise_numpy_scalar_int():
    x = np.int64(5)
    assert serialise(x) == 5


def test_serialise_numpy_scalar_float():
    x = np.float64(3.14)
    assert serialise(x) == 3.14


def test_serialise_numpy_bool():
    x = np.bool_(True)
    assert serialise(x) is True


def test_serialise_numpy_complex():
    x = np.complex64(2 + 3j)
    assert serialise(x) == complex(2 + 3j)


def test_serialise_dict_recursive():
    data = {
        "a": np.int64(1),
        "b": np.array([1, 2]),
        "c": {"d": np.bool_(False)},
    }
    out = serialise(data)
    assert out == {"a": 1, "b": [1, 2], "c": {"d": False}}


def test_serialise_list_tuple():
    data = [np.int64(1), (np.float64(2.0), np.bool_(True))]
    out = serialise(data)
    assert out == [1, [2.0, True]]


def test_serialise_set():
    data = {np.int64(1), np.int64(2)}
    out = serialise(data)
    assert sorted(out) == [1, 2]


def test_serialise_passthrough():
    assert serialise("hello") == "hello"


# =========================
# _infer + deserialise basics
# =========================


def test_deserialise_infer_int():
    assert deserialise("5", inspect.Parameter.empty) == 5


def test_deserialise_infer_float():
    assert deserialise("3.2", inspect.Parameter.empty) == 3.2


def test_deserialise_infer_bool_true():
    assert deserialise("true", inspect.Parameter.empty) is True


def test_deserialise_infer_bool_false():
    assert deserialise("false", inspect.Parameter.empty) is False


def test_deserialise_infer_none():
    assert deserialise("none", inspect.Parameter.empty) is None


def test_deserialise_infer_json_list():
    assert deserialise("[1,2,3]", inspect.Parameter.empty) == [1, 2, 3]


def test_deserialise_infer_json_dict():
    assert deserialise('{"a": 1}', inspect.Parameter.empty) == {"a": 1}


def test_deserialise_infer_fallback_string():
    assert deserialise("hello", inspect.Parameter.empty) == "hello"


def test_deserialise_none_allowed():

    assert deserialise(None, int | None) is None


def test_deserialise_none_not_allowed():
    with pytest.raises(ValueError):
        deserialise(None, int)


def test_deserialise_union():

    assert deserialise("5", int | str) == 5


@pytest.mark.parametrize(
    "val,expected",
    [
        (True, True),
        (1, True),
        (0, False),
        ("true", True),
        ("false", False),
        ("yes", True),
        ("no", False),
    ],
)
def test_deserialise_bool(val, expected):
    assert deserialise(val, bool) == expected


def test_deserialise_bool_invalid():
    with pytest.raises(ValueError):
        deserialise("notabool", bool)


def test_deserialise_int():
    assert deserialise("5", int) == 5
    assert deserialise(5.0, int) == 5


def test_deserialise_int_invalid():
    with pytest.raises(ValueError):
        deserialise("5.5", int)


def test_deserialise_int_bool_rejected():
    with pytest.raises(ValueError):
        deserialise(True, int)


def test_deserialise_float():
    assert deserialise("3.14", float) == 3.14
    assert deserialise(2, float) == 2.0


def test_deserialise_float_invalid():
    with pytest.raises(ValueError):
        deserialise("abc", float)


def test_deserialise_str():
    assert deserialise(123, str) == "123"


def test_deserialise_ndarray_from_string():
    arr = deserialise("[1,2,3]", np.ndarray)
    assert isinstance(arr, np.ndarray)
    assert arr.tolist() == [1, 2, 3]


def test_deserialise_ndarray_from_scalar():
    arr = deserialise(5, np.ndarray)
    assert arr.tolist() == [5]


def test_deserialise_list_annotation():

    result = deserialise("1,2,3", list[int])
    assert result == [1, 2, 3]


def test_deserialise_list_non_list_input():

    result = deserialise(5, list[int])
    assert result == [5]


def test_deserialise_tuple():

    result = deserialise("[1,2]", tuple[int, int])
    assert result == (1, 2)


def test_deserialise_dict():

    result = deserialise('{"a": "1"}', dict[str, int])
    assert result == {"a": 1}


def test_deserialise_fallback_non_string():
    assert deserialise(10, object) == 10
