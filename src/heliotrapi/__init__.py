"""Top level API.

.. data:: __version__
    :type: str

    Version number as calculated by https://github.com/pypa/setuptools_scm
"""

from heliotrapi.analysis_core.decorator import (
    analysis,
    finished_nexus_analysis,
    start_message_analysis,
    started_nexus_analysis,
    stop_message_analysis,
    updated_nexus_analysis,
)
from heliotrapi.task_queue.message_models import NexusMessage, StartMessage, StopMessage

from ._version import __version__

__all__ = [
    "__version__",
    "analysis",
    "finished_nexus_analysis",
    "start_message_analysis",
    "started_nexus_analysis",
    "stop_message_analysis",
    "updated_nexus_analysis",
    "NexusMessage",
    "StartMessage",
    "StopMessage",
]
