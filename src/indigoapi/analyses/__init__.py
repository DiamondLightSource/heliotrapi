import importlib

from indigoapi.analyses.loader import load_analyses, load_plugins
from indigoapi.config import Config

MODULE_NAMES = []


def initialize_analyses(register_all: bool = False):
    """Load built-in analyses and user plugins. Call during server startup."""
    global MODULE_NAMES

    # load built-in analyses
    package = importlib.import_module(__name__)
    MODULE_NAMES = load_analyses(package)

    # load user plugins from config
    config = Config.load_config()
    load_plugins(config, register_all=register_all)
