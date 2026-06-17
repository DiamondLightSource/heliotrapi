"""Top level API.

.. data:: __version__
    :type: str

    Version number as calculated by https://github.com/pypa/setuptools_scm
"""

from heliotrapi.analysis_core.decorator import (
    analysis,
)

from ._version import __version__

__all__ = ["__version__", "analysis"]
