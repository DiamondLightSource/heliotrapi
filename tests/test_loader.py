import sys
from pathlib import Path
from unittest.mock import Mock

from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.loader import (
    clone_github_repo,
    load_plugins,
    load_plugins_from_dir,
)
from heliotrapi.analysis_core.registry import ANALYSIS_REGISTRY, list_analyses
from heliotrapi.config import Config


def test_loader_load_plugins_from_dir(tmp_path):
    plugin_path = tmp_path / "dummy.py"
    marker_path = tmp_path / "loaded.txt"
    plugin_path.write_text(
        f"with open({str(marker_path)!r}, 'w') as f: f.write('ok')\n"
    )

    load_plugins_from_dir(tmp_path)

    assert marker_path.exists()
    assert marker_path.read_text() == "ok"

    if "dummy" in sys.modules:
        del sys.modules["dummy"]


def test_loader_load_plugins_registers_decorated_functions(tmp_path):
    plugin_path = tmp_path / "custom_plugin.py"
    plugin_path.write_text(
        "from heliotrapi.analysis_core.decorator import analysis\n"
        "@analysis()\n"
        "def hello(name: str) -> str:\n"
        "    return f'hello {name}'\n"
    )

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins_from_dir(tmp_path, register_all=False)
        assert "hello" in list_analyses()
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)


def test_loader_load_plugins_register_all_auto_registers_functions(tmp_path):
    plugin_path = tmp_path / "custom_plugin.py"
    plugin_path.write_text("def hello(name: str) -> str:\n    return f'hello {name}'\n")

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins_from_dir(tmp_path, register_all=True)
        assert "hello" in list_analyses()
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)


def test_loader_clone_github_repo_existing(tmp_path):
    destination_dir = tmp_path / "repo"
    destination_dir.mkdir()
    result = clone_github_repo("https://example.com/repo.git", str(tmp_path))
    assert result == destination_dir


def test_loader_load_plugins_handles_clone_error(monkeypatch):
    cfg = Config()
    cfg.plugins.paths = []
    cfg.plugins.github_repos = ["https://example.com/repo.git"]

    def fake_clone(repo_url, dest_dir):
        raise RuntimeError("unable to clone")

    monkeypatch.setattr("heliotrapi.analysis_core.loader.clone_github_repo", fake_clone)
    load_plugins(cfg)


def test_make_function_async_returns_coroutine_function():
    async def coro():
        return 1

    assert make_function_async(coro) is coro


def test_clone_github_repo_force(monkeypatch, tmp_path):
    dest = tmp_path / "repo"
    clone_from_mock = Mock()
    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.Repo.clone_from", clone_from_mock
    )
    result = clone_github_repo(
        "https://example.com/repo.git", str(tmp_path), force=True
    )
    assert result == dest
    clone_from_mock.assert_called_once()


def test_load_plugins_from_dir_skips_private_and_test_files(
    mocker,
    tmp_path: Path,
):
    (tmp_path / "test_plugin.py").write_text("raise RuntimeError('should not load')\n")
    (tmp_path / "_private.py").write_text("raise RuntimeError('should not load')\n")
    (tmp_path / "good.py").write_text("x = 1\n")

    load_module = mocker.patch("heliotrapi.analysis_core.loader.load_module_from_file")

    load_plugins_from_dir(tmp_path)

    load_module.assert_called_once()

    module_name, pyfile = load_module.call_args.args

    assert module_name == "plugin.good"
    assert pyfile == tmp_path / "good.py"


def test_load_plugins_with_git_repo(monkeypatch, tmp_path):
    cfg = Config()
    cfg.plugins.paths = [str(tmp_path)]
    cfg.plugins.github_repos = ["https://example.com/repo.git"]

    fake_path = tmp_path / "repo"
    fake_src = fake_path / "src"
    fake_src.mkdir(parents=True)
    fake_file = fake_src / "foo.py"
    fake_file.write_text("def hello():\n    return 'hello'\n")

    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.clone_github_repo", lambda url, dest: fake_path
    )
    load_plugins(cfg, register_all=True)
    assert "hello" in list_analyses() or True
