import asyncio
import importlib
import inspect
import logging
import pkgutil
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import ParamSpec, TypeVar

from git import Repo

from heliotrapi.analysis_core.registry import register_analysis
from heliotrapi.config import Config

logger = logging.getLogger(__name__)


def load_analyses(package):

    module_names = []

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{module_name}")
        module_names.append(module_name)

    return module_names


P = ParamSpec("P")
R = TypeVar("R")


def get_async_function(func: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    if inspect.iscoroutinefunction(func):
        return func  # type: ignore[return-value]

    @wraps(func)
    async def async_fn(*args: P.args, **kwargs: P.kwargs) -> R:
        return await asyncio.to_thread(func, *args, **kwargs)

    return async_fn


def register_module_functions(module):

    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if not inspect.isfunction(obj):
            continue
        if obj.__module__ != module.__name__:
            continue
        try:
            register_analysis(name, get_async_function(obj))
        except ValueError:
            logger.debug(f"Analysis '{name}' already registered")
        except Exception as e:
            logger.error(f"Unable to register {name} from {module.__name__}: {e}")


def load_plugins_from_dir(path: str | Path, register_all: bool = False):
    """Load user plugins recursively from a folder and all subfolders."""
    path = Path(path)
    assert isinstance(path, Path)
    if not path.exists() or not path.is_dir():
        return

    for pyfile in path.rglob("*.py"):
        if pyfile.stem.startswith("_") or pyfile.stem.startswith("test_"):
            continue

        module_name = f"plugin.{pyfile.relative_to(path).with_suffix('').as_posix().replace('/', '.')}"  # noqa
        try:
            spec = importlib.util.spec_from_file_location(module_name, pyfile)  # type: ignore
            module = importlib.util.module_from_spec(spec)  # type: ignore
            spec.loader.exec_module(module)
            # logger.info(f"Loaded plugin: {pyfile}")
            if register_all:
                register_module_functions(module)

        except Exception:
            # logger.error(f"Failed to read plugin {pyfile}: {e}")
            pass


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


# if __name__ == "__main__":
#     from heliotrapi.analysis_core.registry import list_analyses

#     load_plugins(Config.load_config())

#     print(list_analyses()[0:4])
