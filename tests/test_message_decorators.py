import asyncio
from typing import cast

import pytest

from heliotrapi.analysis_core.decorator import (
    finished_nexus_analysis,
    start_message_analysis,
    started_nexus_analysis,
    stop_message_analysis,
    updated_nexus_analysis,
)
from heliotrapi.analysis_core.message_names import (
    FINISHED_NEXUS_ANALYSIS_NAME,
    START_MESSAGE_ANALYSIS_NAME,
    STARTED_NEXUS_ANALYSIS_NAME,
    STOP_MESSAGE_ANALYSIS_NAME,
)
from heliotrapi.analysis_core.registry import ANALYSIS_REGISTRY
from heliotrapi.models import AnalysisRequest
from heliotrapi.task_queue import QueueManager
from heliotrapi.task_queue.message_models import (
    NexusMessage,
    StartMessage,
    StopMessage,
)
from heliotrapi.task_queue.rabbitmq import (
    _StompListener,
)
from test_message_models import (
    FINISHED_NEXUS_MESSAGE,
    START_MESSAGE,
    STARTED_NEXUS_MESSAGE,
    STOP_MESSAGE,
)


def test_start_message_analysis_decorator():

    message = START_MESSAGE

    @start_message_analysis
    def log_start(message: StartMessage):

        pass

    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    job = listener.stomp_message_to_request(message)

    assert isinstance(job, AnalysisRequest)
    assert job.analysis_name == START_MESSAGE_ANALYSIS_NAME


@pytest.mark.parametrize(
    "message, analysis_name",
    [
        (START_MESSAGE, START_MESSAGE_ANALYSIS_NAME),
        (STOP_MESSAGE, STOP_MESSAGE_ANALYSIS_NAME),
        (STARTED_NEXUS_MESSAGE, STARTED_NEXUS_ANALYSIS_NAME),
        (FINISHED_NEXUS_MESSAGE, FINISHED_NEXUS_ANALYSIS_NAME),
    ],
)
def test_message_analysis_decorators_works_when_function_decorated(
    message: dict, analysis_name: str
):

    @start_message_analysis
    def start_analysis(message: StartMessage):
        pass

    @stop_message_analysis
    def stop_analysis(message: StopMessage):
        pass

    @started_nexus_analysis
    def start_nexus_analysis(message: NexusMessage):
        pass

    @updated_nexus_analysis
    def update_nexus_analysis(message: NexusMessage):
        pass

    @finished_nexus_analysis
    def stop_nexus_analysis(message: NexusMessage):
        pass

    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    job = listener.stomp_message_to_request(message)

    assert isinstance(job, AnalysisRequest)
    assert job.analysis_name == analysis_name

    # cleanup for other tests

    ANALYSIS_REGISTRY.pop(START_MESSAGE_ANALYSIS_NAME)
    ANALYSIS_REGISTRY.pop(STOP_MESSAGE_ANALYSIS_NAME)
    ANALYSIS_REGISTRY.pop(STARTED_NEXUS_ANALYSIS_NAME)
    ANALYSIS_REGISTRY.pop(FINISHED_NEXUS_ANALYSIS_NAME)


@pytest.mark.parametrize(
    "message, analysis_name",
    [
        (START_MESSAGE, START_MESSAGE_ANALYSIS_NAME),
        (STOP_MESSAGE, STOP_MESSAGE_ANALYSIS_NAME),
        (STARTED_NEXUS_MESSAGE, STARTED_NEXUS_ANALYSIS_NAME),
        (FINISHED_NEXUS_MESSAGE, FINISHED_NEXUS_ANALYSIS_NAME),
    ],
)
def test_message_analysis_decorators_returns_none_without_used_decorators(
    message: dict, analysis_name: str
):

    listener = _StompListener(
        queue_manager=cast(QueueManager, None),
        loop=asyncio.new_event_loop(),
    )
    job = listener.stomp_message_to_request(message)

    assert job is None


@pytest.mark.parametrize(
    "message, analysis_name",
    [
        (START_MESSAGE, START_MESSAGE_ANALYSIS_NAME),
        (STOP_MESSAGE, STOP_MESSAGE_ANALYSIS_NAME),
        (STARTED_NEXUS_MESSAGE, STARTED_NEXUS_ANALYSIS_NAME),
        (FINISHED_NEXUS_MESSAGE, FINISHED_NEXUS_ANALYSIS_NAME),
    ],
)
def test_message_analysis_decorators_fails_with_bad_args_but_loads(
    message: dict, analysis_name: str
):

    @start_message_analysis
    def start_analysis(mymessage: StartMessage):
        pass

    @stop_message_analysis
    def stop_analysis(message):
        pass

    @started_nexus_analysis
    def start_nexus_analysis(message: StartMessage):
        pass

    @updated_nexus_analysis
    def update_nexus_analysis(my_message: NexusMessage):
        pass

    @finished_nexus_analysis
    def stop_nexus_analysis(message: NexusMessage, other_args: str):
        pass
