from datetime import datetime

from indigoapi.models import AnalysisRequest, AnalysisResult


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
