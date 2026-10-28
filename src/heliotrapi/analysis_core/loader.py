import importlib
import importlib.util
import inspect
import pkgutil
import subprocess
import sys
import types
from collections.abc import Callable
from pathlib import Path

from git import GitCommandError, Repo
from pydantic import BaseModel

from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.message_names import (
    FINISHED_NEXUS_ANALYSIS_NAME,
    START_MESSAGE_ANALYSIS_NAME,
    STARTED_NEXUS_ANALYSIS_NAME,
    STOP_MESSAGE_ANALYSIS_NAME,
    UPDATED_NEXUS_ANALYSIS_NAME,
)
from heliotrapi.analysis_core.registry import register_analysis
from heliotrapi.config import Config, MessageFunctionsConfig
from heliotrapi.logger import logger
from heliotrapi.task_queue.message_models import (
    NexusMessage,
    StartMessage,
    StopMessage,
)

# MessageFunctionsConfig field -> (registry name, message type the handler takes)
_MESSAGE_HANDLERS: dict[str, tuple[str, type[BaseModel]]] = {
    "start": (START_MESSAGE_ANALYSIS_NAME, StartMessage),
    "stop": (STOP_MESSAGE_ANALYSIS_NAME, StopMessage),
    "nexus_started": (STARTED_NEXUS_ANALYSIS_NAME, NexusMessage),
    "nexus_updated": (UPDATED_NEXUS_ANALYSIS_NAME, NexusMessage),
    "nexus_finished": (FINISHED_NEXUS_ANALYSIS_NAME, NexusMessage),
}


def load_analyses(package: types.ModuleType) -> list[str]:
    """Import every sub-module in *package*, register its public functions and
    return the sub-module names."""
    names: list[str] = []
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{module_name}")
        register_module_functions(module)
        names.append(module_name)
    return names


def register_module_functions(
    module: types.ModuleType, names: set[str] | None = None
) -> None:
    """Register public top-level functions defined in *module*.

    Args:
        module: The module to scan.
        names: If given, only register functions with these names.
    """
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if names is not None and name not in names:
            continue
        if not inspect.isfunction(obj):
            continue
        if obj.__module__ != module.__name__:  # exclude imported functions
            continue
        _try_register(name, obj, module.__name__)


def _try_register(name: str, func: Callable, source: str) -> None:
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


def _plugin_files(root: Path) -> list[Path]:
    return [f for f in sorted(root.rglob("*.py")) if not _should_skip(f.stem)]


def _resolve(root: Path, dotted: str) -> tuple[list[Path], str | None]:
    """Resolve a dotted path under *root* to the files it covers.

    Hyphens are treated as underscores.  The path can name a package
    (``xrpd_toolbox.i15_1``), a module (``xrpd_toolbox.i15_1.attenuation``)
    or a function in a module (``xrpd_toolbox.i15_1.attenuation.my_func``).

    Returns:
        The matching ``.py`` files (empty if nothing matches) and the function
        name, or ``None`` if the path names a package or module.
    """
    parts = dotted.replace("-", "_").split(".")
    target = root.joinpath(*parts)
    if target.is_dir():
        return _plugin_files(target), None
    if target.with_suffix(".py").is_file():
        return [target.with_suffix(".py")], None
    if len(parts) > 1:
        module = root.joinpath(*parts[:-1]).with_suffix(".py")
        if module.is_file():
            return [module], parts[-1]
    return [], None


def _check_message_args(func: Callable, message_type: type[BaseModel]) -> None:
    """Check *func* can be called with every field of *message_type* as kwargs.

    Each field must be a named parameter or be absorbed by ``**kwargs``, and
    every required parameter must be a field.

    Raises:
        TypeError: If the signature does not match.
    """
    params = inspect.signature(func).parameters
    fields = set(message_type.model_fields)
    has_var_kwargs = any(p.kind is p.VAR_KEYWORD for p in params.values())

    unaccepted = fields - set(params)
    if unaccepted and not has_var_kwargs:
        raise TypeError(
            f"{func.__name__} does not accept {sorted(unaccepted)} from "
            f"{message_type.__name__}; add them as parameters or use **kwargs"
        )

    unknown = [
        name
        for name, p in params.items()
        if name not in fields
        and p.default is p.empty
        and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]
    if unknown:
        raise TypeError(
            f"{func.__name__} requires {unknown}, which are not fields of "
            f"{message_type.__name__}"
        )


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


def _import_file(pyfile: Path, root: Path) -> types.ModuleType | None:
    """Import *pyfile* as a plugin module, reusing it if already imported."""
    module_name = _module_name_for(pyfile, root)
    existing = sys.modules.get(module_name)
    if existing is not None and getattr(existing, "__file__", None) == str(pyfile):
        return existing
    try:
        module = _load_module_from_file(module_name, pyfile)
    except Exception as e:
        logger.error("Failed to load plugin '%s'", e)
        return None
    logger.debug("Loaded plugin: %s", pyfile)
    return module


def _find_function(root: Path, dotted: str) -> Callable | None:
    """Import and return the function *dotted* names under *root*, if any."""
    files, func_name = _resolve(root, dotted)
    if not files or func_name is None:
        return None
    module = _import_file(files[0], root)
    func = getattr(module, func_name, None)
    return func if inspect.isfunction(func) else None


def load_plugins_from_dir(
    path: str | Path,
    register_all: bool = False,
    include: list[str] | None = None,
) -> None:
    """Load and register plugin functions from *path*.

    Args:
        path: Directory the dotted paths are relative to (a repo's ``src``).
        register_all: When ``True``, import every ``*.py`` file under *path*
            and register every public top-level function.
        include: Dotted paths of packages, modules or functions to import and
            register when *register_all* is ``False``; nothing else is read.
    """
    root = Path(path)
    if not root.is_dir():
        return

    if register_all:
        for pyfile in _plugin_files(root):
            if module := _import_file(pyfile, root):
                register_module_functions(module)
        return

    for dotted in include or []:
        files, func_name = _resolve(root, dotted)
        if not files:
            logger.error("Could not find '%s' in '%s'", dotted, root)
        elif func_name is None:
            for pyfile in files:
                if module := _import_file(pyfile, root):
                    register_module_functions(module)
        elif func := _find_function(root, dotted):
            _try_register(func_name, func, dotted)
        else:
            logger.error("Could not find function '%s' in '%s'", dotted, root)


def register_message_functions(
    roots: list[Path], message_functions: MessageFunctionsConfig
) -> None:
    """Register the function to run for each STOMP start, stop and nexus message.

    Args:
        roots: Directories to look for the functions in (each repo's ``src``).
        message_functions: Dotted path of the function for each message type,
            relative to whichever root contains it.
    """
    for field, dotted in message_functions:
        if dotted is None:
            continue
        name, message_type = _MESSAGE_HANDLERS[field]
        func = next((f for root in roots if (f := _find_function(root, dotted))), None)
        if func is None:
            logger.error(
                "Could not find function '%s' for %s. Nothing will happen on %s",
                dotted,
                name,
                name,
            )
            continue
        try:
            _check_message_args(func, message_type)
            register_analysis(name, make_function_async(func))
        except Exception as e:
            logger.error(
                "'%s' cannot handle %s: %s. Nothing will happen on %s",
                dotted,
                name,
                e,
                name,
            )


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
        _install_repo_and_dependencies(dest_path, requirements=True)
        logger.debug("Cloned '%s' -> '%s'", repo_url, dest_path)
    else:
        try:
            Repo(dest_path).remotes.origin.pull()
            _install_repo_and_dependencies(dest_path, requirements=True)
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


def load_plugins(config: Config) -> None:
    """Clone (or update) each configured GitHub repo and register its functions.

    Built-in analyses (``heliotrapi.analyses``) are registered by
    ``load_analyses``; this function handles everything external.  Each repo
    uses its own ``register_all`` and ``include`` settings, then the
    ``message_functions`` are looked up across all repos.

    Args:
        config: Application config carrying plugin paths and repo settings.
    """
    repos = config.plugins.github_repos or []
    if repos and not config.plugins.paths:
        logger.error("No plugin path configured to clone GitHub repos into")
        return

    roots: list[Path] = []
    for repo in repos:
        logger.info("Loading plugin repo: %s", repo.url)
        try:
            repo_path = clone_or_update_github_repo(repo.url, config.plugins.paths[0])
        except Exception:
            logger.exception("Unable to clone/update repo '%s'", repo.url)
            continue

        root = repo_path / "src"
        roots.append(root)
        load_plugins_from_dir(
            root, register_all=repo.register_all, include=repo.include
        )

    register_message_functions(roots, config.plugins.message_functions)
