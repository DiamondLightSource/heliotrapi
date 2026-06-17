import time

import pytest
from fastapi.testclient import TestClient

from heliotrapi.api.endpoints import ANALYSE_ROUTE
from heliotrapi.config import Config
from heliotrapi.models import AnalysisRequest
from heliotrapi.server import start_api


def test_analysis_flow_with_post():

    app = start_api()

    # Use context manager to trigger lifespan
    with TestClient(app) as client_http:
        # Now queue_manager exists
        client = TestClient(app)

        request = AnalysisRequest(analysis_name="double", inputs={"number": 21})

        response = client.post(ANALYSE_ROUTE, json=request.model_dump(mode="json"))

        assert response.status_code == 200

        request_id = response.json()["request_id"]

        for _ in range(10):
            r = client_http.get(f"/result/id/{request_id}")

            print(r)

            if r.status_code != 200:
                time.sleep(0.1)
                continue
            else:
                break
        else:
            pytest.fail("Result not ready in time")

        assert r is not None
        data = r.json()

        print(data)

        assert data["status"] == "completed"
        assert data["result"] == 42


def test_empty_config_intialises():

    cfg = Config()
    assert isinstance(cfg, Config)


def test_config_loads_from_file():

    cfg = Config.load_config()
    assert isinstance(cfg, Config)


if __name__ == "__main__":
    test_analysis_flow_with_post()
