import asyncio
import os
import socket
from collections.abc import Awaitable, Callable
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError

from heliotrapi.logger import logger


class SingleInstanceLock:
    """Makes sure only one process at a time runs a given task.

    Used to stop the RabbitMQ listener from running in every uvicorn
    worker process: STOMP topic subscriptions are pub/sub, so every
    subscriber gets every message, and with multiple worker processes each
    would otherwise receive and enqueue the same message. Only the process
    currently holding the lock calls `on_acquire`; if that process dies, the
    lock expires in Redis after `ttl_seconds` and another process's retry
    loop picks it up - no manual failover handling needed.

    Renewing/releasing the lock uses WATCH/MULTI/EXEC (an optimistic
    compare-and-swap) instead of server-side Lua scripting, so a plain
    Redis - or fakeredis in tests, without its optional lupa dependency -
    is enough: a renewal or release only takes effect if the lock still
    holds *this instance's own* token.
    """

    def __init__(
        self,
        redis_client: Redis,
        lock_key: str,
        ttl_seconds: int = 15,
        renew_interval_seconds: float = 5.0,
        retry_interval_seconds: float = 5.0,
    ) -> None:
        self._redis = redis_client
        self.lock_key = lock_key
        self.ttl_seconds = ttl_seconds
        self.renew_interval_seconds = renew_interval_seconds
        self.retry_interval_seconds = retry_interval_seconds
        self.token = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex}"

    async def _renew(self) -> bool:
        """Extend the lock's TTL, but only while it still holds our token.

        Treats a Redis connection failure the same as losing the lock -
        rather than crashing run_while_held's loop - since we can't tell the
        difference from here, and stepping down is the safe choice either
        way.
        """
        async with self._redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(self.lock_key)
                current = await pipe.get(self.lock_key)
                if current != self.token:
                    await pipe.unwatch()
                    return False
                pipe.multi()
                pipe.expire(self.lock_key, self.ttl_seconds)
                await pipe.execute()
                return True
            except WatchError:
                return False
            except RedisError as e:
                logger.warning(f"Could not renew lock '{self.lock_key}': {e}")
                return False

    async def _release(self) -> None:
        """Best-effort immediate release, only if we still hold the lock.

        This is purely an optimization (see run_while_held's docstring) -
        TTL expiry guarantees eventual failover regardless - so a Redis
        connection failure here (e.g. it's already shutting down) is logged
        and swallowed rather than raised.
        """
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(self.lock_key)
                    current = await pipe.get(self.lock_key)
                    if current != self.token:
                        await pipe.unwatch()
                        return
                    pipe.multi()
                    pipe.delete(self.lock_key)
                    await pipe.execute()
                except WatchError:
                    return
        except RedisError as e:
            logger.warning(f"Could not release lock '{self.lock_key}': {e}")

    async def run_while_held(
        self,
        on_acquire: Callable[[], Awaitable[None]],
        on_lose: Callable[[], Awaitable[None]],
    ) -> None:
        """Run until cancelled, calling on_acquire/on_lose as the lock changes hands."""
        holding_lock = False
        try:
            while True:
                if not holding_lock:
                    acquired = await self._redis.set(
                        self.lock_key, self.token, nx=True, ex=self.ttl_seconds
                    )
                    if not acquired:
                        await asyncio.sleep(self.retry_interval_seconds)
                        continue

                    holding_lock = True
                    logger.info(f"Acquired lock '{self.lock_key}' ({self.token})")
                    await on_acquire()

                await asyncio.sleep(self.renew_interval_seconds)

                if not await self._renew():
                    logger.warning(f"Lost lock '{self.lock_key}'; stepping down")
                    holding_lock = False
                    await on_lose()
        finally:
            if holding_lock:
                await on_lose()
                # Let another process take over immediately on graceful
                # shutdown, rather than waiting out the full TTL.
                await self._release()
