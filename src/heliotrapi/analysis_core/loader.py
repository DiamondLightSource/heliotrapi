import importlib
import importlib.util
import inspect
import pkgutil
import subprocess
import sys
import types
from pathlib import Path

from git import GitCommandError, Repo

from heliotrapi import logger
from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.registry import register_analysis
from heliotrapi.config import Config


def load_analyses(package: types.ModuleType) -> list[str]:
    """Import every sub-module in *package* and return their names."""
    names: list[str] = []
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{module_name}")
        names.append(module_name)
    return names


def register_module_functions(module: types.ModuleType) -> None:
    """Register every public top-level function defined in *module*.

    This is an escape hatch for plugins that cannot use the ``@analysis``
    decorator.  Prefer the decorator for explicit, intentional registration.
    """
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if not inspect.isfunction(obj):
            continue
        if obj.__module__ != module.__name__:  # exclude imported functions
            continue
        _try_register(name, obj, module.__name__)


def _try_register(name: str, func: types.FunctionType, source: str) -> None:
    try:
        register_analysis(name, make_function_async(func))
    except ValueError:
        logger.debug("Analysis '%s' already registered (skipping)", name)
    except Exception:
        logger.exception("Unable to register '%s' from '%s'", name, source)


def _run_uv(cmd: list[str]) -> None:
    """Run a uv command, raising ``CalledProcessError`` with output on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )
    logger.debug("uv output:\n%s", result.stdout)


def _add_src_to_path(repo_path: Path) -> None:
    """Add *repo_path*/src (or *repo_path* itself) to ``sys.path`` if not present.

    This allows intra-repo imports to resolve for repos that are not installed
    as packages (i.e. have no ``pyproject.toml``).
    """
    src = repo_path / "src"
    inject = src if src.is_dir() else repo_path
    inject_str = str(inject)
    if inject_str not in sys.path:
        sys.path.insert(0, inject_str)
        logger.debug("Added '%s' to sys.path for intra-repo imports", inject)


def _install_repo_and_dependencies(repo_path: Path, requirements: bool = True) -> None:
    """Install a plugin repo's dependencies using ``uv pip install``.

    Resolution order:

    1. ``pyproject.toml`` present -> ``uv pip install <repo_path>``
       Installs the package *and* its declared dependencies, making intra-repo
       imports (e.g. ``from xrpd_toolbox.utils.utils import fn``) work via the
       normal import system.

    2. ``requirements.txt`` only -> ``uv pip install -r requirements.txt``
       Installs third-party deps, then falls back to ``sys.path`` injection
       so intra-repo imports still resolve.

    3. Neither found -> ``sys.path`` injection only.

    Raises:
        subprocess.CalledProcessError: If the ``uv`` install command fails.
    """
    req_file = repo_path / "requirements.txt"
    pyproject = repo_path / "pyproject.toml"

    if pyproject.exists():
        cmd = ["uv", "pip", "install", str(repo_path)]
        if not requirements:
            cmd.append("--no-deps")
        logger.info("Installing plugin package from '%s'", repo_path)
        _run_uv(cmd)
        if requirements and req_file.exists():
            logger.info("Installing extra dependencies from '%s'", req_file)
            _run_uv(["uv", "pip", "install", "-r", str(req_file)])
        return

    if requirements and req_file.exists():
        logger.info("Installing plugin dependencies from '%s'", req_file)
        _run_uv(["uv", "pip", "install", "-r", str(req_file)])
    elif requirements:
        logger.debug("No dependency file found in '%s'", repo_path)

    _add_src_to_path(repo_path)


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------

_SKIP_PREFIXES = ("_", "test_")


def _should_skip(stem: str) -> bool:
    return any(stem.startswith(p) for p in _SKIP_PREFIXES)


def _module_name_for(pyfile: Path, root: Path) -> str:
    relative = pyfile.relative_to(root).with_suffix("")
    return "plugin." + relative.as_posix().replace("/", ".")


def _load_module_from_file(module_name: str, pyfile: Path) -> types.ModuleType:
    """Load and execute a Python file as a module.

    Raises:
        ImportError: If the spec cannot be created, a named dependency is
            missing (with a helpful install hint), or the module raises an
            ImportError during execution.
    """
    spec = importlib.util.spec_from_file_location(module_name, pyfile)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for '{pyfile}'")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        # Remove the module and any submodules registered during partial execution
        stale = [
            k
            for k in sys.modules
            if k == module_name or k.startswith(f"{module_name}.")
        ]
        for k in stale:
            sys.modules.pop(k, None)

        if isinstance(exc, ImportError) and exc.name:
            raise ImportError(
                f"Plugin '{pyfile.name}' requires a missing dependency: '{exc.name}'. "
                f"Install it with: uv pip install {exc.name}"
            ) from exc

        raise ImportError(f"Plugin '{pyfile.name}' failed to load: {exc}") from exc

    return module


def load_plugins_from_dir(path: str | Path, register_all: bool = False) -> None:
    """Recursively load Python plugins from *path*.

    Plugin authors should decorate functions with ``@analysis`` for explicit
    registration.  Set *register_all* only for legacy or third-party plugins
    that cannot be modified.

    Args:
        path: Directory to search for ``*.py`` files.
        register_all: When ``True``, auto-register every public top-level
            function in each module in addition to ``@analysis``-decorated ones.
    """
    root = Path(path)
    if not root.is_dir():
        return

    for pyfile in sorted(root.rglob("*.py")):
        if _should_skip(pyfile.stem):
            continue

        module_name = _module_name_for(pyfile, root)
        try:
            module = _load_module_from_file(module_name, pyfile)
        except ImportError:
            logger.exception("Failed to load plugin '%s'", pyfile)
            continue
        except Exception:
            logger.exception("Unexpected error loading plugin '%s'", pyfile)
            continue

        logger.debug("Loaded plugin: %s", pyfile)
        if register_all:
            register_module_functions(module)


def clone_or_update_github_repo(repo_url: str, dest_dir: str | Path) -> Path:
    """Clone *repo_url* into *dest_dir*, or pull if already present.

    Dependencies are installed via ``uv pip install`` on first clone only.
    Subsequent pulls do **not** re-install; restart the process after updating
    a repo if its dependencies have changed.

    Returns:
        Path to the local repo directory.

    Raises:
        git.GitCommandError: If cloning fails.
        subprocess.CalledProcessError: If dependency installation fails.
    """
    dest_path = Path(dest_dir) / Path(repo_url).stem
    is_new = not dest_path.exists()

    if is_new:
        Repo.clone_from(repo_url, dest_path)
        logger.debug("Cloned '%s' -> '%s'", repo_url, dest_path)
        _install_repo_and_dependencies(dest_path, requirements=True)
    else:
        try:
            Repo(dest_path).remotes.origin.pull()
            logger.debug("Pulled latest for '%s'", dest_path.name)
        except GitCommandError:
            logger.warning(
                "Could not pull '%s'; using existing copy. "
                "Dependencies may be out of date.",
                dest_path.name,
            )
        # Re-inject sys.path for repos without pyproject.toml on every load,
        # since sys.path is not persisted between process restarts.
        if not (dest_path / "pyproject.toml").exists():
            _add_src_to_path(dest_path)

    return dest_path


def load_plugins(config: Config, register_all: bool = False) -> None:
    """Load all external plugins from configured local paths and GitHub repos.

    Built-in analyses (``heliotrapi.analyses``) are already registered via
    decorators; this function handles everything external.

    Args:
        config: Application config carrying plugin paths and repo URLs.
        register_all: When ``False``, only ``@analysis``-decorated functions
            are registered.  When ``True``, every public top-level function
            is also auto-registered.  Prefer ``False``; set ``True`` only for
            third-party plugins that cannot use the decorator.
    """
    for plugin_path in config.plugins.paths:
        load_plugins_from_dir(plugin_path, register_all=register_all)

    for repo_url in config.plugins.github_repos or []:
        logger.info("Loading plugin repo: %s", repo_url)
        try:
            repo_path = clone_or_update_github_repo(repo_url, config.plugins.paths[0])
        except Exception:
            logger.exception("Unable to clone/update repo '%s'", repo_url)
            continue

        load_plugins_from_dir(repo_path / "src", register_all=register_all)
