import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from indigoapi.main import start_api
from indigoapi.models import AnalysisResult


def test_api_health_and_endpoints_routes():
    app = start_api()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        response = client.get("/endpoints")
        assert response.status_code == 200
        assert any(route["path"] == "/health" for route in response.json())


def test_api_result_latest_and_not_found():
    app = start_api()
    with TestClient(app) as client:
        result = AnalysisResult(
            request_id=uuid.uuid4(),
            analysis_name="double",
            status="completed",
            result=10,
            created_at=datetime.now(),
            finished_at=datetime.now(),
        )
        client.app.state.queue_manager.latest_result = result  # type: ignore

        latest_response = client.get("/result/latest")
        assert latest_response.status_code == 200
        assert latest_response.json()["status"] == "completed"

        missing_response = client.get("/result/id/00000000-0000-0000-0000-000000000000")
        assert missing_response.status_code == 404
