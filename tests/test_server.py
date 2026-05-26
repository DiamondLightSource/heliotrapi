from pathlib import Path

from fastapi.testclient import TestClient

from heliotrapi.server import start_api


def test_start_api_serves_root_index():
    app = start_api()
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "HeliotrAPI" in response.text or "<html" in response.text


def test_start_api_serve_index_default_message(monkeypatch):
    original_exists = Path.exists

    def fake_exists(self):
        if self.name == "index.html":
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    app = start_api()
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["message"].startswith("HeliotrAPI Analysis")
