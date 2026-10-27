import importlib

import pytest

from heliotrapi.analysis_core.loader import load_analyses


def pytest_configure():
    package = importlib.import_module("heliotrapi.analyses")
    load_analyses(package)


@pytest.fixture(autouse=True)
def isolated_results_db(tmp_path, monkeypatch):
    # stop the server writing results to results.db in the repo, and
    # give each test a fresh store
    from heliotrapi import server

    monkeypatch.setattr(server.config.results, "db_path", str(tmp_path / "results.db"))
