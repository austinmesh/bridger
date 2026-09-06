import asyncio

import pytest

from bridger.meshtastic import DeviceModel

HARDWARE = [
    {"hwModel": 1, "displayName": "TLORA V2"},
    {"hwModel": 1, "displayName": "TLORA V2 (alt)"},
    {"hwModel": 43, "displayName": "HELTEC V3"},
]


class FakeSession:
    """Minimal stand-in for ClientSession.get() as an async context manager.

    Counts calls and holds each response open until released, so a stampede shows up as a
    call count rather than as a timing flake.
    """

    def __init__(self, payload, delay=0):
        self.payload = payload
        self.delay = delay
        self.calls = 0

    def get(self, url):
        self.calls += 1
        return self._Response(self.payload, self.delay)

    class _Response:
        def __init__(self, payload, delay):
            self.payload = payload
            self.delay = delay

        async def __aenter__(self):
            if self.delay:
                await asyncio.sleep(self.delay)
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def json(self):
            return self.payload


@pytest.fixture(autouse=True)
async def clear_request_cache():
    """The @cached_stampede cache is built once at import, so it is shared across tests."""
    await DeviceModel.make_request.cache.clear()
    yield
    await DeviceModel.make_request.cache.clear()


class TestDeviceModel:
    async def test_make_request_caches_across_instances(self):
        # noself=True means the cache key ignores self, so a second DeviceModel reuses the entry.
        session = FakeSession(HARDWARE)

        assert await DeviceModel(session=session).make_request() == HARDWARE
        assert await DeviceModel(session=session).make_request() == HARDWARE
        assert session.calls == 1

    async def test_concurrent_cold_requests_fetch_once(self):
        """Regression for the cache stampede plain @cached allowed.

        The routes share one DeviceModel, so a burst against a cold cache used to fetch the
        upstream API once per caller.
        """
        session = FakeSession(HARDWARE, delay=0.05)
        device = DeviceModel(session=session)

        results = await asyncio.gather(*(device.make_request() for _ in range(5)))

        assert results == [HARDWARE] * 5
        assert session.calls == 1

    async def test_get_displaynames_filters_by_model(self):
        device = DeviceModel(session=FakeSession(HARDWARE))

        assert await device.get_displaynames(1) == ["TLORA V2", "TLORA V2 (alt)"]
        assert await device.get_displaynames(43) == ["HELTEC V3"]
        assert await device.get_displaynames(999) == []

    async def test_get_all_displaynames_groups_by_hw_model(self):
        device = DeviceModel(session=FakeSession(HARDWARE))

        assert await device.get_all_displaynames() == [
            {"hw_model": 1, "names": "TLORA V2, TLORA V2 (alt)"},
            {"hw_model": 43, "names": "HELTEC V3"},
        ]

    async def test_get_all_displaynames_as_list(self):
        device = DeviceModel(session=FakeSession(HARDWARE))

        assert await device.get_all_displaynames(names_as_list=True) == [
            {"hw_model": 1, "names": ["TLORA V2", "TLORA V2 (alt)"]},
            {"hw_model": 43, "names": ["HELTEC V3"]},
        ]
