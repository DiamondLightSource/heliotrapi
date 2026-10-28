import asyncio
import sys
from typing import cast

import pytest

from heliotrapi.analysis_core.loader import register_message_functions
from heliotrapi.analysis_core.message_names import (
    FINISHED_NEXUS_ANALYSIS_NAME,
    START_MESSAGE_ANALYSIS_NAME,
    STARTED_NEXUS_ANALYSIS_NAME,
    STOP_MESSAGE_ANALYSIS_NAME,
    UPDATED_NEXUS_ANALYSIS_NAME,
)
from heliotrapi.analysis_core.registry import ANALYSIS_REGISTRY
from heliotrapi.config import MessageFunctionsConfig
from heliotrapi.models import AnalysisRequest
from heliotrapi.task_queue import QueueManager
from heliotrapi.task_queue.rabbitmq import _StompListener
from test_message_models import (
    FINISHED_NEXUS_MESSAGE,
    START_MESSAGE,
    STARTED_NEXUS_MESSAGE,
    STOP_MESSAGE,
)

MESSAGE_NAMES = [
    START_MESSAGE_ANALYSIS_NAME,
    STOP_MESSAGE_ANALYSIS_NAME,
    STARTED_NEXUS_ANALYSIS_NAME,
    UPDATED_NEXUS_ANALYSIS_NAME,
    FINISHED_NEXUS_ANALYSIS_NAME,
]

GOOD_HANDLERS = """\
from heliotrapi.task_queue.message_models import RunStartDoc, RunStopDoc


def on_start(name: str, doc: RunStartDoc, task_id: str):
    pass


def on_stop(doc: RunStopDoc, **kwargs):
    pass


def on_nexus_started(**kwargs):
    pass


def on_nexus_updated(status: str, file_path: str, **kwargs):
    pass


def on_nexus_finished(file_path: str, scan_number: int, **kwargs):
    pass
"""

BAD_HANDLERS = """\
def on_start(name, doc):  # missing task_id
    pass


def on_stop(message):  # not a StopMessage field
    pass


def on_nexus_started(status, file_path):  # missing the other fields
    pass


def on_nexus_updated(not_a_field, **kwargs):
    pass


def on_nexus_finished(scan_number, other_args, **kwargs):
    pass
"""

ALL_MESSAGES = MessageFunctionsConfig(
    start="pkg.handlers.on_start",
    stop="pkg.handlers.on_stop",
    nexus_started="pkg.handlers.on_nexus_started",
    nexus_updated="pkg.handlers.on_nexus_updated",
    nexus_finished="pkg.handlers.on_nexus_finished",
)


@pytest.fixture
def handlers_dir(tmp_path):
    (tmp_path / "pkg").mkdir()
    yield tmp_path
    for name in MESSAGE_NAMES:
        ANALYSIS_REGISTRY.pop(name, None)
    for k in [k for k in sys.modules if k.startswith("plugin.")]:
        del sys.modules[k]


def _listener() -> _StompListener:
    return _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )


@pytest.mark.parametrize(
    "message, analysis_name",
    [
        (START_MESSAGE, START_MESSAGE_ANALYSIS_NAME),
        (STOP_MESSAGE, STOP_MESSAGE_ANALYSIS_NAME),
        (STARTED_NEXUS_MESSAGE, STARTED_NEXUS_ANALYSIS_NAME),
        (FINISHED_NEXUS_MESSAGE, FINISHED_NEXUS_ANALYSIS_NAME),
    ],
)
def test_message_handlers_from_config_are_dispatched(
    handlers_dir, message: dict, analysis_name: str
):
    (handlers_dir / "pkg" / "handlers.py").write_text(GOOD_HANDLERS)

    register_message_functions([handlers_dir], ALL_MESSAGES)

    job = _listener().stomp_message_to_request(message)
    assert isinstance(job, AnalysisRequest)
    assert job.analysis_name == analysis_name


def test_message_handlers_are_not_registered_as_analyses(handlers_dir):
    (handlers_dir / "pkg" / "handlers.py").write_text(GOOD_HANDLERS)

    register_message_functions(
        [handlers_dir], MessageFunctionsConfig(start="pkg.handlers.on_start")
    )

    assert START_MESSAGE_ANALYSIS_NAME in ANALYSIS_REGISTRY
    assert STOP_MESSAGE_ANALYSIS_NAME not in ANALYSIS_REGISTRY
    assert "on_start" not in ANALYSIS_REGISTRY
    assert "on_stop" not in ANALYSIS_REGISTRY


@pytest.mark.parametrize(
    "message",
    [START_MESSAGE, STOP_MESSAGE, STARTED_NEXUS_MESSAGE, FINISHED_NEXUS_MESSAGE],
)
def test_message_returns_none_without_configured_handlers(message: dict):
    assert _listener().stomp_message_to_request(message) is None


@pytest.mark.parametrize(
    "message",
    [START_MESSAGE, STOP_MESSAGE, STARTED_NEXUS_MESSAGE, FINISHED_NEXUS_MESSAGE],
)
def test_message_handlers_with_bad_args_are_not_registered(handlers_dir, message: dict):
    (handlers_dir / "pkg" / "handlers.py").write_text(BAD_HANDLERS)

    register_message_functions([handlers_dir], ALL_MESSAGES)

    assert _listener().stomp_message_to_request(message) is None


def test_missing_message_handler_is_ignored(handlers_dir):
    register_message_functions(
        [handlers_dir], MessageFunctionsConfig(start="pkg.handlers.nope")
    )

    assert START_MESSAGE_ANALYSIS_NAME not in ANALYSIS_REGISTRY


def test_message_function_found_in_second_repo(tmp_path):
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    repo_a.mkdir()
    (repo_b / "pkg").mkdir(parents=True)
    (repo_b / "pkg" / "handlers.py").write_text(GOOD_HANDLERS)
    try:
        register_message_functions(
            [repo_a, repo_b], MessageFunctionsConfig(start="pkg.handlers.on_start")
        )
        assert START_MESSAGE_ANALYSIS_NAME in ANALYSIS_REGISTRY
    finally:
        ANALYSIS_REGISTRY.pop(START_MESSAGE_ANALYSIS_NAME, None)
        for k in [k for k in sys.modules if k.startswith("plugin.")]:
            del sys.modules[k]


@pytest.mark.asyncio
async def test_message_function_is_called_with_message_fields(handlers_dir):
    (handlers_dir / "pkg" / "handlers.py").write_text(
        "CALLS = []\n"
        "def on_stop(name, doc, task_id):\n"
        "    CALLS.append((name, doc.exit_status, task_id))\n"
    )
    register_message_functions(
        [handlers_dir], MessageFunctionsConfig(stop="pkg.handlers.on_stop")
    )

    job = _listener().stomp_message_to_request(STOP_MESSAGE)
    assert isinstance(job, AnalysisRequest)
    assert set(job.inputs) == {"name", "doc", "task_id"}

    await ANALYSIS_REGISTRY[STOP_MESSAGE_ANALYSIS_NAME](**job.inputs)
    calls = sys.modules["plugin.pkg.handlers"].CALLS
    assert calls == [
        ("stop", STOP_MESSAGE["doc"]["exit_status"], STOP_MESSAGE["task_id"])
    ]
