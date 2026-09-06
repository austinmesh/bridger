import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Optional

from aiocache import SimpleMemoryCache

from bridger.log import logger


class TTLCache[T]:
    """A TTL cache over a blocking loader, with single-flight loading.

    Discord callbacks run on the event loop, so every blocking InfluxDB or EMQX call has to
    be handed to a worker thread. Autocomplete makes that acute: it fires per keystroke
    against a ~3s deadline, so N keystrokes must collapse into one query rather than N.

    Values are stored wrapped in a 1-tuple because aiocache cannot distinguish a cached None
    from a miss, and some loaders (get_node_info for an unknown node) legitimately return None.
    """

    def __init__(self, ttl: int, name: str = "cache"):
        self.ttl = ttl
        self.name = name
        self._cache = SimpleMemoryCache()
        self._locks: dict[str, asyncio.Lock] = {}
        self._waiters: dict[str, int] = {}

    @asynccontextmanager
    async def _key_lock(self, key: str):
        """Hold a per-key lock, dropping it once nobody is waiting.

        Refcounted rather than left in the dict: keys can be unbounded (one per mesh node),
        and a lock per node seen would leak for the lifetime of the process.
        """
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()

        self._waiters[key] = self._waiters.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._waiters[key] -= 1
            if self._waiters[key] == 0:
                del self._waiters[key]
                self._locks.pop(key, None)

    async def _load(self, key: str, loader: Callable[[], T]) -> T:
        value = await asyncio.to_thread(loader)
        await self._cache.set(key, (value,), ttl=self.ttl)
        return value

    async def get_or_load(self, key: str, loader: Callable[[], T]) -> T:
        cached = await self._cache.get(key)
        if cached is not None:
            return cached[0]

        async with self._key_lock(key):
            # Somebody may have populated it while we waited for the lock.
            cached = await self._cache.get(key)
            if cached is not None:
                return cached[0]

            logger.debug(f"{self.name}: loading {key!r}")
            return await self._load(key, loader)

    async def refresh(self, key: str, loader: Callable[[], T]) -> T:
        """Reload unconditionally, e.g. from a background refresh task."""
        async with self._key_lock(key):
            return await self._load(key, loader)

    async def invalidate(self, key: Optional[str] = None) -> None:
        """Drop one key, or the whole cache when key is None."""
        if key is None:
            await self._cache.clear()
        else:
            await self._cache.delete(key)
