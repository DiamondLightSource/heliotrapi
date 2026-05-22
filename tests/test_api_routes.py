import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from indigoapi.models import AnalysisResult
from indigoapi.server import start_api


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


def test_api_latest_result_not_found():
    app = start_api()
    with TestClient(app) as client:
        response = client.get("/result/latest")
        assert response.status_code == 404
        assert response.json()["detail"] == "No results yet"


def test_api_result_by_id_and_all_results():
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
        client.app.state.queue_manager.results[result.request_id] = result  # type: ignore

        response = client.get(f"/result/id/{result.request_id}")
        assert response.status_code == 200
        assert response.json()["analysis_name"] == "double"

        all_response = client.get("/results/all")
        assert all_response.status_code == 200
        assert len(all_response.json()) == 1
        assert all_response.json()[0]["analysis_name"] == "double"
