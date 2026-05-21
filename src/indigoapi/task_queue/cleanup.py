import asyncio
import time


async def cleanup_results(queue_manager, ttl: int, interval: int):
    """
    Remove expired results from memory.
    ttl = time to live
    interval = poll period

    checks every interval
    if live time > ttl. delete
    """

    while True:
        now = time.time()

        expired = [
            rid for rid, (_, ts) in queue_manager.results.items() if now - ts > ttl
        ]

        for rid in expired:
            del queue_manager.results[rid]

        await asyncio.sleep(interval)
