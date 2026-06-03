"""Top level API.

.. data:: __version__
    :type: str

    Version number as calculated by https://github.com/pypa/setuptools_scm
"""

import logging

from ._version import __version__

__all__ = ["__version__"]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S %d-%m-%Y",
)
logger = logging.getLogger(__name__)
