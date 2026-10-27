import asyncio
from typing import Any

from heliotrapi.logger import logger


async def cleanup_results(queue_manager: Any, ttl: int, interval: int) -> None:
    """Remove expired results from the result store.

    Every `interval` seconds, deletes results finished (or created, if not
    finished) more than `ttl` seconds ago.
    """

    while True:
        deleted = queue_manager.results.delete_expired(ttl)
        if deleted:
            logger.info(f"Cleaned up {deleted} expired results")

        await asyncio.sleep(interval)
