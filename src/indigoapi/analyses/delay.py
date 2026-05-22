import time

from indigoapi.analysis_core.decorator import analysis


@analysis()
def delay(seconds: float):
    """Simulate a long-running analysis by sleeping for specified number of seconds."""

    time.sleep(seconds)
    return f"Slept for {seconds} seconds"
