import asyncio
import time

import pytest

from bridger.cogs.cache import TTLCache


@pytest.fixture
def cache():
    return TTLCache(ttl=60, name="test")


class TestGetOrLoad:
    async def test_loads_once_and_then_serves_from_cache(self, cache):
        calls = []

        def loader():
            calls.append(1)
            return "value"

        assert await cache.get_or_load("k", loader) == "value"
        assert await cache.get_or_load("k", loader) == "value"
        assert len(calls) == 1

    async def test_caches_none(self, cache):
        # aiocache treats a cached None as a miss, and get_node_info returns None for unknown
        # nodes, so without the wrapper every unknown node would re-query on every packet.
        calls = []

        def loader():
            calls.append(1)
            return None

        assert await cache.get_or_load("k", loader) is None
        assert await cache.get_or_load("k", loader) is None
        assert len(calls) == 1

    async def test_concurrent_callers_trigger_a_single_load(self, cache):
        calls = []

        def loader():
            calls.append(1)
            time.sleep(0.05)  # blocking, as the real InfluxDB and EMQX clients are
            return "value"

        results = await asyncio.gather(*(cache.get_or_load("k", loader) for _ in range(10)))

        assert results == ["value"] * 10
        assert len(calls) == 1

    async def test_different_keys_load_independently(self, cache):
        await cache.get_or_load("a", lambda: 1)
        await cache.get_or_load("b", lambda: 2)

        assert await cache.get_or_load("a", lambda: 99) == 1
        assert await cache.get_or_load("b", lambda: 99) == 2

    async def test_loader_runs_off_the_event_loop(self, cache):
        loop = asyncio.get_running_loop()
        ran_on = {}

        def loader():
            # A running loop in this thread would mean the blocking call is on the event loop.
            try:
                ran_on["loop"] = asyncio.get_running_loop()
            except RuntimeError:
                ran_on["loop"] = None
            return "value"

        await cache.get_or_load("k", loader)

        assert ran_on["loop"] is None
        assert loop.is_running()

    async def test_a_failing_loader_propagates_and_caches_nothing(self, cache):
        with pytest.raises(RuntimeError):
            await cache.get_or_load("k", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        assert await cache.get_or_load("k", lambda: "recovered") == "recovered"


class TestExpiryAndInvalidation:
    async def test_expired_entries_reload(self):
        cache = TTLCache(ttl=1, name="test")
        calls = []

        def loader():
            calls.append(1)
            return len(calls)

        assert await cache.get_or_load("k", loader) == 1
        await asyncio.sleep(1.1)
        assert await cache.get_or_load("k", loader) == 2

    async def test_refresh_reloads_unconditionally(self, cache):
        await cache.get_or_load("k", lambda: "first")
        assert await cache.refresh("k", lambda: "second") == "second"
        assert await cache.get_or_load("k", lambda: "third") == "second"

    async def test_invalidate_one_key(self, cache):
        await cache.get_or_load("a", lambda: 1)
        await cache.get_or_load("b", lambda: 2)

        await cache.invalidate("a")

        assert await cache.get_or_load("a", lambda: 99) == 99
        assert await cache.get_or_load("b", lambda: 99) == 2

    async def test_invalidate_everything(self, cache):
        await cache.get_or_load("a", lambda: 1)
        await cache.get_or_load("b", lambda: 2)

        await cache.invalidate()

        assert await cache.get_or_load("a", lambda: 99) == 99
        assert await cache.get_or_load("b", lambda: 99) == 99


class TestLockBookkeeping:
    async def test_locks_do_not_accumulate(self, cache):
        # Keys are unbounded in practice (one per mesh node), so a lock left behind per key
        # would leak for the lifetime of the process.
        for i in range(50):
            await cache.get_or_load(str(i), lambda: "value")

        assert cache._locks == {}
        assert cache._waiters == {}

    async def test_locks_released_after_a_failed_load(self, cache):
        with pytest.raises(RuntimeError):
            await cache.get_or_load("k", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        assert cache._locks == {}
        assert cache._waiters == {}
