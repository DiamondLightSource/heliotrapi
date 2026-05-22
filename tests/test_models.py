from datetime import datetime

import pytest

from heliotrapi.models import AnalysisRequest, AnalysisResponse, AnalysisResult


def test_analysis_request_item_access():
    request = AnalysisRequest(analysis_name="double", inputs={"number": 10})
    assert request["analysis_name"] == "double"
    assert request["inputs"] == {"number": 10}
    assert isinstance(request.request_id, type(request["request_id"]))


def test_analysis_result_item_access():
    result = AnalysisResult(
        request_id=AnalysisRequest(analysis_name="double", inputs={}).request_id,
        analysis_name="double",
        status="completed",
        result=42,
        created_at=datetime.now(),
        finished_at=datetime.now(),
    )
    assert result["status"] == "completed"
    assert result["result"] == 42


def test_analysis_request_defaults():
    request = AnalysisRequest(analysis_name="double", inputs={})
    assert request.request_id is not None
    assert request.created_at is not None


def test_analysis_response_is_accepted():
    response = AnalysisResponse(analysis_name="double", accepted=True)
    assert response.is_accepted()


def test_analysis_response_rejects_unaccepted():
    response = AnalysisResponse(
        analysis_name="double", accepted=False, details="invalid"
    )

    with pytest.raises(ValueError, match="was not accepted"):
        response.is_accepted()
