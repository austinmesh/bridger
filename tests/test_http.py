from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from bridger.http import create_app


@pytest_asyncio.fixture
async def test_client(aiohttp_client):
    with patch("bridger.http.DeviceModel") as mock_device:
        mock_instance = AsyncMock()
        mock_device.return_value = mock_instance
        app = create_app()
        app["device"] = mock_instance  # Set state before starting client to avoid deprecation warning
        client = await aiohttp_client(app)
        yield client


@pytest.mark.asyncio
class TestHttpAPI:
    async def test_index_view_lists_routes(self, test_client):
        resp = await test_client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "Bridger API" in text
        assert "/model/displaynames" in text

    async def test_get_displaynames(self, test_client):
        test_client.app["device"].get_displaynames.return_value = ["Test Board"]
        resp = await test_client.get("/model/displaynames/1")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data == ["Test Board"]

    async def test_get_displaynames_all(self, test_client):
        test_client.app["device"].get_all_displaynames.return_value = [{"hw_model": 1, "names": ["Device A"]}]
        resp = await test_client.get("/model/displaynames")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data == [{"hw_model": 1, "names": ["Device A"]}]
