import asyncio
import time
from typing import Any

from heliotrapi.models import AnalysisResult


def _extract_timestamp(value: Any) -> float | None:
    """Return a POSIX timestamp for supported stored result formats, or None.

    Supported formats:
    - legacy tuples: (result, timestamp)
    - AnalysisResult instances (use finished_at or created_at)
    - dict-like serialized entries with keys "finished_at" or "created_at"
    """

    # Legacy tuple: (result, timestamp)
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[1], (int, float))
    ):
        return float(value[1])

    # AnalysisResult instance
    if isinstance(value, AnalysisResult):
        dt = value.finished_at or value.created_at
        if dt is None:
            return None
        try:
            return dt.timestamp()
        except Exception:
            return None

    # dict-like serialized entry
    if isinstance(value, dict):
        for key in ("finished_at", "created_at"):
            candidate = value.get(key)
            if candidate is None:
                continue
            if isinstance(candidate, (int, float)):
                return float(candidate)
            try:
                return candidate.timestamp()
            except Exception:
                continue

    return None


async def cleanup_results(queue_manager: Any, ttl: int, interval: int) -> None:
    """Remove expired results from memory.

    The function polls `queue_manager.results` every `interval` seconds and
    deletes entries older than `ttl` seconds. `queue_manager` is accepted as
    a loose `Any` to allow test fakes that provide a `results` mapping.
    """

    while True:
        now = time.time()

        expired: list = []

        for rid, value in list(queue_manager.results.items()):
            ts = _extract_timestamp(value)
            if ts is None:
                continue
            if now - ts > ttl:
                expired.append(rid)

        for rid in expired:
            queue_manager.results.pop(rid, None)

        await asyncio.sleep(interval)
