import sys

from indigoapi.analysis_core.loader import (
    clone_github_repo,
    load_plugins,
    load_plugins_from_dir,
)
from indigoapi.analysis_core.registry import ANALYSIS_REGISTRY, list_analyses
from indigoapi.config import Config


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
        "from indigoapi.analysis_core.decorator import analysis\n"
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

    monkeypatch.setattr("indigoapi.analysis_core.loader.clone_github_repo", fake_clone)
    load_plugins(cfg)
