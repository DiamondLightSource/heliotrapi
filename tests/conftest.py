import importlib

from heliotrapi.analysis_core.loader import load_analyses


def pytest_configure():
    package = importlib.import_module("heliotrapi.analyses")
    load_analyses(package)
