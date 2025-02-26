from collections import defaultdict

from aiocache import cached
from aiohttp import ClientSession

BASE_URL = "https://api.meshtastic.org"


class DeviceModel:
    device_hardware_path = "/resource/deviceHardware"

    def __init__(self, session: ClientSession = None):
        self.session = session

    @cached(ttl=3600)  # Cache the response for 1 hour
    async def make_request(self) -> list:
        async with self.session.get(BASE_URL + self.device_hardware_path) as response:
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
