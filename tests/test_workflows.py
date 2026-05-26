import pytest

from heliotrapi.analyses.workflows import Workflows


def test_workflows_not_implemented():
    with pytest.raises(NotImplementedError):
        Workflows()
