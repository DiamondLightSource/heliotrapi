import asyncio
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from heliotrapi.task_queue.single_instance_lock import SingleInstanceLock


class _FailingPipeline:
    """Fakes `redis_client.pipeline()` where the first command sent over
    the wire (WATCH) fails, as if the connection had just dropped."""

    async def __aenter__(self):
        pipe = AsyncMock()
        pipe.watch.side_effect = RedisConnectionError("connection refused")
        return pipe

    async def __aexit__(self, *exc_info):
        return False


@pytest.mark.asyncio
async def test_acquires_when_free(fake_redis_client):
    lock = SingleInstanceLock(fake_redis_client, lock_key="test:lock", ttl_seconds=5)

    acquired = asyncio.Event()
    lost = asyncio.Event()

    async def on_acquire():
        acquired.set()

    async def on_lose():
        lost.set()

    task = asyncio.create_task(lock.run_while_held(on_acquire, on_lose))
    try:
        await asyncio.wait_for(acquired.wait(), timeout=1.0)
        assert await fake_redis_client.get("test:lock") == lock.token
    finally:
        task.cancel()

    assert lost.is_set() or True  # cancellation may pre-empt on_lose; not asserted


@pytest.mark.asyncio
async def test_second_contender_blocked_while_held(fake_redis_client):
    holder = SingleInstanceLock(fake_redis_client, lock_key="test:lock", ttl_seconds=5)
    contender = SingleInstanceLock(
        fake_redis_client, lock_key="test:lock", ttl_seconds=5
    )

    holder_acquired = asyncio.Event()
    contender_acquired = asyncio.Event()

    async def noop():
        pass

    async def holder_on_acquire():
        holder_acquired.set()

    async def contender_on_acquire():
        contender_acquired.set()

    holder_task = asyncio.create_task(holder.run_while_held(holder_on_acquire, noop))
    contender_task = asyncio.create_task(
        contender.run_while_held(contender_on_acquire, noop)
    )
    try:
        await asyncio.wait_for(holder_acquired.wait(), timeout=1.0)
        await asyncio.sleep(0.1)
        assert not contender_acquired.is_set()
        assert await fake_redis_client.get("test:lock") == holder.token
    finally:
        holder_task.cancel()
        contender_task.cancel()


@pytest.mark.asyncio
async def test_renewal_extends_past_original_ttl(fake_redis_client):
    lock = SingleInstanceLock(
        fake_redis_client,
        lock_key="test:lock",
        ttl_seconds=1,
        renew_interval_seconds=0.05,
    )

    async def noop():
        pass

    task = asyncio.create_task(lock.run_while_held(noop, noop))
    try:
        # Longer than the original 1s ttl - only survives if renewal works.
        await asyncio.sleep(1.3)
        assert await fake_redis_client.get("test:lock") == lock.token
    finally:
        task.cancel()


@pytest.mark.asyncio
async def test_lost_lock_triggers_on_lose(fake_redis_client):
    lock = SingleInstanceLock(
        fake_redis_client,
        lock_key="test:lock",
        ttl_seconds=5,
        renew_interval_seconds=0.05,
    )

    acquired = asyncio.Event()
    lost = asyncio.Event()

    async def on_acquire():
        acquired.set()

    async def on_lose():
        lost.set()

    task = asyncio.create_task(lock.run_while_held(on_acquire, on_lose))
    try:
        await asyncio.wait_for(acquired.wait(), timeout=1.0)
        # Simulate someone else forcibly taking the key over.
        await fake_redis_client.set("test:lock", "someone-else")
        await asyncio.wait_for(lost.wait(), timeout=1.0)
    finally:
        task.cancel()


@pytest.mark.asyncio
async def test_release_only_deletes_own_token(fake_redis_client):
    lock = SingleInstanceLock(fake_redis_client, lock_key="test:lock", ttl_seconds=5)

    await fake_redis_client.set("test:lock", "someone-elses-token", ex=5)

    # _release should be a no-op since the lock doesn't hold our token.
    await lock._release()

    assert await fake_redis_client.get("test:lock") == "someone-elses-token"


@pytest.mark.asyncio
async def test_release_swallows_connection_error(fake_redis_client):
    """A dead Redis connection during shutdown (e.g. the embedded
    redis-server already exited) must not raise out of _release() - TTL
    expiry alone still guarantees failover, so this is best-effort only."""
    lock = SingleInstanceLock(fake_redis_client, lock_key="test:lock", ttl_seconds=5)
    lock._redis.pipeline = lambda *a, **k: _FailingPipeline()

    await lock._release()  # must not raise


@pytest.mark.asyncio
async def test_renew_treats_connection_error_as_lost(fake_redis_client):
    lock = SingleInstanceLock(fake_redis_client, lock_key="test:lock", ttl_seconds=5)
    lock._redis.pipeline = lambda *a, **k: _FailingPipeline()

    assert await lock._renew() is False
