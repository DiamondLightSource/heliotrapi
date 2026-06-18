import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from heliotrapi.api.endpoints import (
    ENDPOINTS_ROUTE,
    HEALTH_ROUTE,
    RESULT_BY_ID_ROUTE,
    RESULT_LATEST_ROUTE,
    RESULTS_ALL_ROUTE,
)
from heliotrapi.models import AnalysisResult
from heliotrapi.server import start_api


def test_health_route_is_healthz():

    assert HEALTH_ROUTE == "/healthz"


def test_resultd_by_id_wont_clash():

    split_url = RESULT_BY_ID_ROUTE.split("/")
    split_url.remove("")
    assert len(split_url) == 3


def test_api_health_and_endpoints_routes():
    app = start_api()
    with TestClient(app) as client:
        response = client.get(HEALTH_ROUTE)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        response = client.get(ENDPOINTS_ROUTE)
        assert response.status_code == 200
        assert any(route["path"] == HEALTH_ROUTE for route in response.json())


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

        latest_response = client.get(RESULT_LATEST_ROUTE)
        assert latest_response.status_code == 200
        assert latest_response.json()["status"] == "completed"

        result_url = RESULT_BY_ID_ROUTE.format(
            request_id="00000000-0000-0000-0000-000000000000"
        )

        missing_response = client.get(result_url)
        assert missing_response.status_code == 404


def test_api_latest_result_not_found():
    app = start_api()
    with TestClient(app) as client:
        response = client.get(RESULT_LATEST_ROUTE)
        assert response.status_code == 404
        assert response.json()["detail"] == "No results yet"


def test_api_result_by_id():
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

        result_url = RESULT_BY_ID_ROUTE.format(request_id=result.request_id)

        response = client.get(result_url)
        assert response.status_code == 200
        assert response.json()["analysis_name"] == "double"


def test_api_result_all_results():
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

        all_response = client.get(RESULTS_ALL_ROUTE)

        print(all_response.json())

        assert all_response.status_code == 200
        assert len(all_response.json()) == 1
        assert all_response.json()[0]["analysis_name"] == "double"
