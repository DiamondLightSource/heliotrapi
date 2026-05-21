import importlib

from indigoapi.analysis_core.loader import load_analyses


def pytest_configure():
    package = importlib.import_module("indigoapi.analyses")
    load_analyses(package)
