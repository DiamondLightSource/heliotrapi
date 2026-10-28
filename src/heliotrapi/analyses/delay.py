import time


def delay(seconds: float):
    """Simulate a long-running analysis by sleeping for specified number of seconds."""

    time.sleep(seconds)
    return f"Slept for {seconds} seconds"
