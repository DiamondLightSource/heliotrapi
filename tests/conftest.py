import importlib

import fakeredis
import pytest

from heliotrapi.analysis_core.loader import load_analyses


def pytest_configure():
    package = importlib.import_module("heliotrapi.analyses")
    load_analyses(package)


@pytest.fixture(autouse=True)
def fake_redis_client(monkeypatch):
    """Back QueueManager/SingleInstanceLock with an isolated in-memory Redis.

    Every redis_service.build_client() call in a test gets a fresh fakeredis
    instance, so no real Redis is needed to run the suite and nothing leaks
    between tests.
    """
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr("heliotrapi.redis_service.build_client", lambda config: fake)
    return fake
