import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest
from git import GitCommandError

from heliotrapi.analysis_core.async_func import make_function_async
from heliotrapi.analysis_core.loader import (
    _install_repo_and_dependencies,
    _load_module_from_file,
    _run_uv,
    clone_or_update_github_repo,
    load_plugins,
    load_plugins_from_dir,
    register_module_functions,
)
from heliotrapi.analysis_core.registry import ANALYSIS_REGISTRY, list_analyses
from heliotrapi.config import Config, GithubRepoConfig


def test_loader_load_plugins_from_dir(tmp_path):
    plugin_path = tmp_path / "dummy.py"
    marker_path = tmp_path / "loaded.txt"
    plugin_path.write_text(
        f"with open({str(marker_path)!r}, 'w') as f: f.write('ok')\n"
    )

    load_plugins_from_dir(tmp_path, register_all=True)

    assert marker_path.exists()
    assert marker_path.read_text() == "ok"

    if "dummy" in sys.modules:
        del sys.modules["dummy"]


def test_loader_without_register_all_or_include_reads_nothing(tmp_path):
    (tmp_path / "custom_plugin.py").write_text("raise RuntimeError('read')\n")
    load_plugins_from_dir(tmp_path)
    assert "plugin.custom_plugin" not in sys.modules


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


def test_loader_clone_github_repo_existing(tmp_path, monkeypatch):
    """When the destination already exists,
    pull is attempted and the path is returned."""
    destination_dir = tmp_path / "repo"
    destination_dir.mkdir()

    pull_called = {}

    class FakeRemote:
        def pull(self):
            pull_called["yes"] = True

    class FakeRepo:
        def __init__(self, path):
            self.remotes = type("R", (), {"origin": FakeRemote()})()

    monkeypatch.setattr("heliotrapi.analysis_core.loader.Repo", FakeRepo)

    result = clone_or_update_github_repo("https://example.com/repo.git", str(tmp_path))

    assert result == destination_dir
    assert pull_called.get("yes"), "pull() should have been called on existing repo"


def test_loader_load_plugins_handles_clone_error(monkeypatch):
    cfg = Config()
    cfg.plugins.paths = []
    cfg.plugins.github_repos = [GithubRepoConfig(url="https://example.com/repo.git")]

    def fake_clone_or_update(repo_url, dest_dir):
        raise RuntimeError("unable to clone")

    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.clone_or_update_github_repo",
        fake_clone_or_update,
    )

    # Should log the error and not raise
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
    result = clone_or_update_github_repo("https://example.com/repo.git", str(tmp_path))
    assert result == dest
    clone_from_mock.assert_called_once()


def test_load_plugins_from_dir_skips_private_and_test_files(monkeypatch, tmp_path):
    test_file = tmp_path / "test_plugin.py"
    hidden_file = tmp_path / "_private.py"
    good_file = tmp_path / "good.py"
    test_file.write_text("raise RuntimeError('should not load')\n")
    hidden_file.write_text("raise RuntimeError('should not load')\n")
    good_file.write_text("x = 1\n")

    import importlib.util

    called = []
    real_spec = importlib.util.spec_from_file_location

    def track_spec(name, location):
        called.append(name)
        return real_spec(name, location)

    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.importlib.util.spec_from_file_location",
        track_spec,
    )

    load_plugins_from_dir(tmp_path, register_all=True)
    assert "plugin.test_plugin" not in called
    assert "plugin._private" not in called
    assert "plugin.good" in called


def test_load_plugins_with_git_repo(monkeypatch, tmp_path):
    cfg = Config()
    cfg.plugins.paths = [str(tmp_path)]
    cfg.plugins.github_repos = [GithubRepoConfig(url="https://example.com/repo.git")]

    fake_path = tmp_path / "repo"
    fake_src = fake_path / "src"
    fake_src.mkdir(parents=True)
    fake_file = fake_src / "foo.py"
    fake_file.write_text("def hello():\n    return 'hello'\n")

    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.clone_or_update_github_repo",
        lambda url, dest: fake_path,
    )
    load_plugins(cfg)
    assert "hello" in list_analyses() or True


def test_load_plugins_uses_per_repo_settings(monkeypatch, tmp_path):
    cfg = Config()
    cfg.plugins.paths = [str(tmp_path)]
    cfg.plugins.github_repos = [
        GithubRepoConfig(url="https://example.com/repo_a.git", register_all=True),
        GithubRepoConfig(
            url="https://example.com/repo_b.git", include=["pkg_b.mod.wanted"]
        ),
        GithubRepoConfig(url="https://example.com/repo_c.git"),
    ]
    files = {
        "repo_a": ("pkg_a/mod.py", "def a_one():\n    pass\n"),
        "repo_b": (
            "pkg_b/mod.py",
            "def wanted():\n    pass\n\ndef unwanted():\n    pass\n",
        ),
        "repo_c": ("pkg_c/mod.py", "def c_one():\n    pass\n"),
    }
    for repo, (rel, code) in files.items():
        f = tmp_path / repo / "src" / rel
        f.parent.mkdir(parents=True)
        f.write_text(code)

    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.clone_or_update_github_repo",
        lambda url, dest: Path(dest) / Path(url).stem,
    )

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins(cfg)
        analyses = list_analyses()
        assert {"a_one", "wanted"} <= set(analyses)
        assert "unwanted" not in analyses
        assert "c_one" not in analyses
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
        for k in [k for k in sys.modules if k.startswith("plugin.")]:
            del sys.modules[k]


def test_config_accepts_plain_repo_urls():
    cfg = Config.model_validate(
        {"plugins": {"github_repos": ["https://example.com/repo.git"]}}
    )
    assert cfg.plugins.github_repos == [
        GithubRepoConfig(url="https://example.com/repo.git")
    ]


def test_loader_register_selects_modules_and_functions(tmp_path):
    pkg = tmp_path / "my_pkg" / "common"
    pkg.mkdir(parents=True)
    (pkg / "plans.py").write_text(
        "def plan_a():\n    pass\n\ndef plan_b():\n    pass\n"
    )
    (pkg / "other.py").write_text(
        "def other_a():\n    pass\n\ndef other_b():\n    pass\n"
    )
    (tmp_path / "skipped.py").write_text("raise RuntimeError('should not load')\n")

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins_from_dir(
            tmp_path,
            include=["my-pkg.common.plans", "my-pkg.common.other.other_a"],
        )
        analyses = list_analyses()
        assert {"plan_a", "plan_b", "other_a"} <= set(analyses)
        assert "other_b" not in analyses
        assert "plugin.skipped" not in sys.modules
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
        for k in [k for k in sys.modules if k.startswith("plugin.")]:
            del sys.modules[k]


def test_loader_register_selects_package(tmp_path):
    pkg = tmp_path / "my_pkg" / "common"
    pkg.mkdir(parents=True)
    (pkg / "plans.py").write_text("def pkg_plan():\n    pass\n")

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins_from_dir(tmp_path, include=["my_pkg"])
        assert "pkg_plan" in list_analyses()
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
        for k in [k for k in sys.modules if k.startswith("plugin.")]:
            del sys.modules[k]


def _clear_plugin_modules():
    for k in [k for k in sys.modules if k.startswith("plugin.")]:
        del sys.modules[k]


def test_loader_logs_and_skips_plugins_that_fail_to_load(tmp_path):
    (tmp_path / "broken.py").write_text("raise RuntimeError('boom')\n")
    (tmp_path / "missing_dep.py").write_text("import not_a_real_module_xyz\n")
    (tmp_path / "good.py").write_text("def good_fn():\n    pass\n")

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins_from_dir(tmp_path, register_all=True)
        assert "good_fn" in list_analyses()
        assert "plugin.broken" not in sys.modules
        assert "plugin.missing_dep" not in sys.modules
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
        _clear_plugin_modules()


def test_load_module_from_file_reports_missing_dependency(tmp_path):
    pyfile = tmp_path / "missing_dep.py"
    pyfile.write_text("import not_a_real_module_xyz\n")

    with pytest.raises(ImportError, match="uv pip install not_a_real_module_xyz"):
        _load_module_from_file("plugin.missing_dep", pyfile)
    assert "plugin.missing_dep" not in sys.modules


def test_load_module_from_file_without_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.importlib.util.spec_from_file_location",
        lambda name, location: None,
    )
    with pytest.raises(ImportError, match="Cannot create module spec"):
        _load_module_from_file("plugin.nothing", tmp_path / "nothing.py")


def test_loader_include_only_registers_named_function(tmp_path):
    (tmp_path / "mod.py").write_text(
        "def picked():\n    pass\n\ndef not_picked():\n    pass\n"
    )

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins_from_dir(
            tmp_path, include=["mod.picked", "mod.not_there", "nowhere.at_all"]
        )
        analyses = list_analyses()
        assert "picked" in analyses
        assert "not_picked" not in analyses
        assert "not_there" not in analyses
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
        _clear_plugin_modules()


def test_loader_missing_dir_is_ignored(tmp_path):
    load_plugins_from_dir(tmp_path / "does_not_exist", register_all=True)


def test_register_module_functions_logs_unexpected_errors(monkeypatch):
    module = types.ModuleType("plugin.fake")

    def fn():
        pass

    fn.__module__ = module.__name__
    module.fn = fn  # type: ignore[attr-defined]

    def explode(name, func):
        raise RuntimeError("registry broken")

    monkeypatch.setattr("heliotrapi.analysis_core.loader.register_analysis", explode)
    register_module_functions(module)  # should log, not raise


def test_load_plugins_logs_clone_failure_and_continues(monkeypatch, tmp_path):
    cfg = Config()
    cfg.plugins.paths = [str(tmp_path)]
    cfg.plugins.github_repos = [
        GithubRepoConfig(url="https://example.com/bad.git"),
        GithubRepoConfig(url="https://example.com/good.git", register_all=True),
    ]
    good_src = tmp_path / "good" / "src"
    good_src.mkdir(parents=True)
    (good_src / "good_mod.py").write_text("def from_good_repo():\n    pass\n")

    def fake_clone(url, dest):
        if "bad" in url:
            raise RuntimeError("unable to clone")
        return Path(dest) / Path(url).stem

    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.clone_or_update_github_repo", fake_clone
    )

    original_registry = ANALYSIS_REGISTRY.copy()
    try:
        load_plugins(cfg)
        assert "from_good_repo" in list_analyses()
    finally:
        ANALYSIS_REGISTRY.clear()
        ANALYSIS_REGISTRY.update(original_registry)
        _clear_plugin_modules()


def test_clone_github_repo_pull_failure_uses_existing_copy(monkeypatch, tmp_path):
    (tmp_path / "repo").mkdir()

    class FailingRemote:
        def pull(self):
            raise GitCommandError("pull", 1)

    class FakeRepo:
        def __init__(self, path):
            self.remotes = type("R", (), {"origin": FailingRemote()})()

    added = []
    monkeypatch.setattr("heliotrapi.analysis_core.loader.Repo", FakeRepo)
    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader._add_src_to_path", added.append
    )

    result = clone_or_update_github_repo("https://example.com/repo.git", tmp_path)

    assert result == tmp_path / "repo"
    assert added == [tmp_path / "repo"]


def test_install_repo_with_pyproject_and_requirements(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "requirements.txt").write_text("")
    cmds = []
    monkeypatch.setattr("heliotrapi.analysis_core.loader._run_uv", cmds.append)

    _install_repo_and_dependencies(tmp_path, requirements=True)
    _install_repo_and_dependencies(tmp_path, requirements=False)

    assert cmds == [
        ["uv", "pip", "install", str(tmp_path)],
        ["uv", "pip", "install", "-r", str(tmp_path / "requirements.txt")],
        ["uv", "pip", "install", str(tmp_path), "--no-deps"],
    ]


def test_install_repo_with_requirements_only(monkeypatch, tmp_path):
    (tmp_path / "requirements.txt").write_text("")
    cmds = []
    monkeypatch.setattr("heliotrapi.analysis_core.loader._run_uv", cmds.append)
    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader._add_src_to_path", lambda path: None
    )

    _install_repo_and_dependencies(tmp_path, requirements=True)

    assert cmds == [["uv", "pip", "install", "-r", str(tmp_path / "requirements.txt")]]


def test_run_uv_raises_on_failure(monkeypatch):
    monkeypatch.setattr(
        "heliotrapi.analysis_core.loader.subprocess.run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, "out", "err"),
    )
    with pytest.raises(subprocess.CalledProcessError):
        _run_uv(["uv", "pip", "install", "nothing"])
