import importlib
import inspect
import pkgutil
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from git import Repo

from heliotrapi import logger
from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.registry import register_analysis
from heliotrapi.config import Config


def load_analyses(package: types.ModuleType) -> list[str]:

    module_names = []

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{module_name}")
        module_names.append(module_name)

    return module_names


def register_module_functions(module):

    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if not inspect.isfunction(obj):
            continue
        if obj.__module__ != module.__name__:
            continue
        try:
            register_analysis(name, make_function_async(obj))
        except ValueError:
            logger.debug(f"Analysis '{name}' already registered")
        except Exception as e:
            logger.error(f"Unable to register {name} from {module.__name__}: {e}")


def load_module_from_file(module_name: str, pyfile: Path) -> types.ModuleType:
    """Load and execute a Python file as a module.

    Raises:
        ImportError: If the module cannot be loaded.
    """
    spec = spec_from_file_location(module_name, pyfile)

    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for '{pyfile}'")

    module = module_from_spec(spec)

    # Make the module visible during execution. Required by
    # dataclasses, typing.get_type_hints(), Pydantic, etc.
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        # Don't leave a partially imported module behind.
        sys.modules.pop(module_name, None)
        raise

    return module


def load_plugins_from_dir(path: str | Path, register_all: bool = False):
    """Load user plugins recursively from a folder and all subfolders."""
    path = Path(path)

    if not path.is_dir():
        return

    for pyfile in sorted(path.rglob("*.py")):
        if pyfile.stem.startswith("_") or pyfile.stem.startswith("test_"):
            continue

        module_name = f"plugin.{pyfile.relative_to(path).with_suffix('').as_posix().replace('/', '.')}"  # noqa

        try:
            module = load_module_from_file(module_name, pyfile)

            logger.debug("Loaded plugin: %s", pyfile)

            if register_all:
                register_module_functions(module)

        except Exception:
            logger.exception("Failed to read plugin '%s'", pyfile)


def clone_github_repo(repo_url: str, dest_dir: str, force: bool = False) -> Path:
    """Clone a repo if not already cloned. Returns path to cloned repo."""
    dest_path = Path(dest_dir) / Path(repo_url).stem

    if not dest_path.exists() or force:
        Repo.clone_from(repo_url, dest_path)

    return dest_path


def load_plugins(config: Config, register_all: bool = False):
    """
    Load all user plugins from configured paths and GitHub repos.

    Built-in analyses (in heliotrapi.analyses) are already loaded via decorators.
    This function loads external plugins.

    Args:
        config: Configuration object with plugin paths and GitHub repos
        register_all: If False, only load @analysis-decorated functions.
                     If True, also auto-register any top-level functions.
    """
    # Load from local plugin paths
    for p in config.plugins.paths:
        load_plugins_from_dir(p, register_all=register_all)

    # Load from GitHub repos
    if config.plugins.github_repos is not None:
        for repo in config.plugins.github_repos:
            logger.info(f"Loading from {repo}")

            try:
                repo_path = clone_github_repo(
                    repo, config.plugins.paths[0]
                )  # cloned into plugins/
                source_path = repo_path / "src"
                load_plugins_from_dir(source_path, register_all=register_all)

            except Exception as e:
                logger.error(f"Unable to load {repo}: {e}")
