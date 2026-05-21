import uuid
from unittest.mock import Mock

import numpy as np
import pytest

from indigoapi.client import AnalysisClient
from indigoapi.models import AnalysisResult
from indigoapi.utils.serialisers import serialise


def test_serialise():

    converted = serialise(
        {
            "x": np.array([1, 2]),
            "n": np.int64(3),
            "f": np.float32(4.5),
            "nested": {"t": np.int32(7)},
            "seq": (np.int16(8),),
        }
    )

    assert converted["x"] == [1, 2]
    assert converted["n"] == 3
    assert converted["f"] == 4.5
    assert converted["nested"]["t"] == 7
    assert converted["seq"] == [8]


def test_client_submit_and_latest_request_id():
    response_id = str(uuid.uuid4())
    response = Mock()
    response.json.return_value = {"request_id": response_id}
    response.raise_for_status = Mock()

    session = Mock()
    session.post.return_value = response

    client = AnalysisClient(base_url="http://test", session=session)
    request_id = client.submit("double", x=np.array([1, 2]))

    assert str(request_id) == response_id
    assert client.latest_request_id == request_id
    session.post.assert_called_once()


def test_client_request_result_404():
    response = Mock(status_code=404)
    response.raise_for_status = Mock()
    session = Mock()
    session.get.return_value = response

    client = AnalysisClient(session=session)
    assert client.request_result(uuid.uuid4()) is None


def test_client_get_result_no_latest():
    client = AnalysisClient(session=Mock())
    result = client.get_result()

    assert result.status == "error"
    assert result.analysis_name == ""


def test_client_get_request_id_result_timeout(monkeypatch):
    client = AnalysisClient(session=Mock())
    client.request_result = Mock(return_value=None)

    times = [0.0, 0.0, 0.1, 0.2]

    def fake_time():
        return times.pop(0)

    monkeypatch.setattr("indigoapi.client.time.time", fake_time)
    monkeypatch.setattr("indigoapi.client.time.sleep", lambda _: None)

    with pytest.raises(TimeoutError):
        client.get_request_id_result(uuid.uuid4(), timeout=0.05, poll_interval=0.01)


def test_client_health_and_endpoints():
    health_response = Mock()
    health_response.status_code = 200
    health_response.json.return_value = {"status": "ok"}
    health_response.raise_for_status = Mock()

    endpoints_response = Mock()
    endpoints_response.status_code = 200
    endpoints_response.json.return_value = [{"path": "/health", "methods": ["GET"]}]
    endpoints_response.raise_for_status = Mock()

    session = Mock()
    session.get.side_effect = [health_response, endpoints_response]

    client = AnalysisClient(base_url="http://test", session=session)
    assert client.health() == {"status": "ok"}
    assert client.get_endpoints() == [{"path": "/health", "methods": ["GET"]}]


def test_client_list_analyses_as_strings():
    session = Mock()
    session.get.return_value.json.return_value = [
        {
            "name": "gaussian_fit",
            "parameters": [
                {"name": "x", "annotation": "np.ndarray", "default": None},
                {"name": "y", "annotation": "np.ndarray", "default": None},
            ],
            "return_annotation": "AnalysisResult",
        }
    ]
    session.get.return_value.status_code = 200
    session.get.return_value.raise_for_status = Mock()

    client = AnalysisClient(base_url="http://test", session=session)
    signatures = client.list_analyses(as_strings=True)

    assert isinstance(signatures, list)
    assert isinstance(signatures[0], str)
    assert signatures[0].startswith("gaussian_fit(\n")
    assert "-> AnalysisResult:" in signatures[0]


def test_client_get_result_success():
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "request_id": str(uuid.uuid4()),
        "analysis_name": "double",
        "status": "completed",
        "result": 4,
        "created_at": "2024-01-01T00:00:00",
        "finished_at": "2024-01-01T00:00:01",
    }

    session = Mock()
    session.get.return_value = response

    client = AnalysisClient(session=session)
    result = client.get_result(timeout=0.5, poll_interval=0.01)

    assert isinstance(result, AnalysisResult)
    assert result.analysis_name == "double"


def test_client_get_last_submitted_result():
    request_id = uuid.uuid4()
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {
        "request_id": str(request_id),
        "analysis_name": "double",
        "status": "completed",
        "result": 4,
        "created_at": "2024-01-01T00:00:00",
        "finished_at": "2024-01-01T00:00:01",
    }

    session = Mock()
    session.get.return_value = response

    client = AnalysisClient(session=session)
    client.latest_request_id = request_id
    result = client.get_last_submitted_result(timeout=0.5, poll_interval=0.01)

    assert isinstance(result, AnalysisResult)
    assert result.request_id == request_id
