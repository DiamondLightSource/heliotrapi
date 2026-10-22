import pytest
from fastapi.testclient import TestClient

from heliotrapi import server
from heliotrapi.api.endpoints import (
    ANALYSE_ROUTE,
    ANALYSES_ROUTE,
    ENDPOINTS_ROUTE,
    HEALTH_ROUTE,
    RESULT_BY_ID_ROUTE,
    RESULT_LATEST_ROUTE,
    RESULTS_ALL_ROUTE,
    STREAM_ROUTE,
)
from heliotrapi.config import AuthConfig, Config
from heliotrapi.models import AnalysisRequest, AnalysisStreamRequest
from heliotrapi.server import start_api

ANALYSIS_REQUEST = AnalysisRequest(
    analysis_name="double", inputs={"number": 21}
).model_dump(mode="json")


@pytest.fixture
def auth_config(monkeypatch):
    def _set(**kwargs) -> None:
        monkeypatch.setattr(server, "config", Config(auth=AuthConfig(**kwargs)))

    return _set


def test_analyse_without_credentials_is_rejected(auth_config):
    auth_config()
    with TestClient(start_api()) as client:
        response = client.post(ANALYSE_ROUTE, json=ANALYSIS_REQUEST)

    assert response.status_code == 401
    # this header is what makes browsers show their login prompt
    assert response.headers["WWW-Authenticate"] == "Basic"


@pytest.mark.parametrize(
    "credentials", [("admin", "wrong"), ("wrong", "password"), ("", "")]
)
def test_analyse_with_wrong_credentials_is_rejected(auth_config, credentials):
    auth_config()
    with TestClient(start_api()) as client:
        response = client.post(ANALYSE_ROUTE, json=ANALYSIS_REQUEST, auth=credentials)

    assert response.status_code == 401


def test_analyse_with_correct_credentials_is_accepted(auth_config):
    auth_config(username="alice", password="secret")
    with TestClient(start_api()) as client:
        response = client.post(
            ANALYSE_ROUTE, json=ANALYSIS_REQUEST, auth=("alice", "secret")
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_analyse_is_open_when_auth_disabled(auth_config):
    auth_config(enabled=False)
    with TestClient(start_api()) as client:
        response = client.post(ANALYSE_ROUTE, json=ANALYSIS_REQUEST)

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_stream_without_credentials_is_rejected(auth_config):
    auth_config()
    stream_request = AnalysisStreamRequest(
        analysis_name="double", inputs={"number": 1}, max_iterations=1
    ).model_dump(mode="json")

    with TestClient(start_api()) as client:
        response = client.request("GET", STREAM_ROUTE, json=stream_request)

    assert response.status_code == 401


RESULT_ROUTES = [
    RESULT_LATEST_ROUTE,
    RESULT_BY_ID_ROUTE.format(request_id="00000000-0000-0000-0000-000000000000"),
    RESULTS_ALL_ROUTE,
]


@pytest.mark.parametrize("route", RESULT_ROUTES)
def test_results_without_credentials_are_rejected(auth_config, route):
    auth_config()
    with TestClient(start_api()) as client:
        response = client.get(route)

    assert response.status_code == 401


@pytest.mark.parametrize("route", RESULT_ROUTES)
def test_results_with_credentials_are_allowed(auth_config, route):
    auth_config()
    with TestClient(start_api()) as client:
        response = client.get(route, auth=("admin", "password"))

    # no results have been stored, so 404 is fine - it just mustn't be 401
    assert response.status_code in (200, 404)


@pytest.mark.parametrize("route", RESULT_ROUTES)
def test_results_are_open_when_auth_disabled(auth_config, route):
    auth_config(enabled=False)
    with TestClient(start_api()) as client:
        response = client.get(route)

    assert response.status_code in (200, 404)


@pytest.mark.parametrize("route", [HEALTH_ROUTE, ANALYSES_ROUTE, ENDPOINTS_ROUTE])
def test_discovery_routes_do_not_need_credentials(auth_config, route):
    auth_config()
    with TestClient(start_api()) as client:
        response = client.get(route)

    assert response.status_code == 200
