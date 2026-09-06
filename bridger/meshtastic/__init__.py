from collections import defaultdict

from aiocache import cached_stampede
from aiohttp import ClientSession

from bridger.config import MESHTASTIC_API_CACHE_TTL, MESHTASTIC_API_ENDPOINT, MESHTASTIC_API_TIMEOUT


class DeviceModel:
    device_hardware_path = "/resource/deviceHardware"

    def __init__(self, session: ClientSession = None):
        self.session = session

    # Stampede-protected rather than plain @cached: the HTTP routes share one DeviceModel, so
    # concurrent requests against a cold cache would each fetch the upstream API. The lease
    # covers the client timeout, so the lock cannot expire while a fetch is still in flight.
    @cached_stampede(lease=MESHTASTIC_API_TIMEOUT, ttl=MESHTASTIC_API_CACHE_TTL, noself=True)
    async def make_request(self) -> list:
        async with self.session.get(MESHTASTIC_API_ENDPOINT + self.device_hardware_path) as response:
            return await response.json()

    async def get_models(self, model_id: int = None) -> list:
        response = await self.make_request()
        return [model for model in response if model["hwModel"] == model_id]

    async def get_displaynames(self, model_id: int) -> list:
        models = await self.get_models(model_id)
        return [model["displayName"] for model in models]

    async def get_all_displaynames(self, names_as_list=False) -> list:
        models_dict = defaultdict(list)
        response = await self.make_request()
        for model in response:
            models_dict[int(model["hwModel"])].append(model["displayName"])

        if names_as_list:
            result = [{"hw_model": hwModel, "names": names} for hwModel, names in models_dict.items()]
        else:
            result = [{"hw_model": hwModel, "names": ", ".join(names)} for hwModel, names in models_dict.items()]

        return result
