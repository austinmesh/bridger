from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

from bridger.config import EMQX_HTTP_TIMEOUT

from .api import ApiMixin
from .authentication import AuthenticationMixin
from .authorization import AuthorizationMixin


class EMQXClient(ApiMixin, AuthenticationMixin, AuthorizationMixin):
    def __init__(self, base_url, api_key, secret_key, prefix="/api/v5", timeout=EMQX_HTTP_TIMEOUT):
        self.base_url = base_url
        self.prefix = prefix
        self.auth = HTTPBasicAuth(api_key, secret_key)
        self.timeout = timeout

    def _handle_response(self, response):
        response.raise_for_status()

        if response.status_code in [204]:
            return response.text
        return response.json()

    def _request(self, method, endpoint, data=None, params=None, timeout=None) -> requests.Response:
        url = urljoin(self.base_url, f"{self.prefix}{endpoint}")
        headers = {"Content-Type": "application/json"}
        response = requests.request(
            method,
            url,
            auth=self.auth,
            headers=headers,
            json=data,
            params=params,
            timeout=self.timeout if timeout is None else timeout,
        )
        return response
