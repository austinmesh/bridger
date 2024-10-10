from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

from .api import ApiMixin
from .authentication import AuthenticationMixin
from .authorization import AuthorizationMixin


class EMQXClient(ApiMixin, AuthenticationMixin, AuthorizationMixin):
    def __init__(self, base_url, api_key, secret_key, prefix="/api/v5"):
        self.base_url = base_url
        self.prefix = prefix
        self.auth = HTTPBasicAuth(api_key, secret_key)

    def _handle_response(self, response):
        response.raise_for_status()

        if response.status_code in [204]:
            return response.text
        return response.json()

    def _request(self, method, endpoint, data=None, params=None) -> requests.Response:
        url = urljoin(self.base_url, f"{self.prefix}{endpoint}")
        headers = {"Content-Type": "application/json"}
        response = requests.request(method, url, auth=self.auth, headers=headers, json=data, params=params)
        return response
