from typing import Any, Union

import requests


class AuthorizationMixin:
    def _request(self, method: str, endpoint: str, data: Any = None, params: Any = None) -> requests.Response: ...
    def _handle_response(self, response: requests.Response) -> Any: ...
    def get_user_authorization_rules_built_in_database(self, username) -> Union[str, list, dict]:
        endpoint = f"/authorization/sources/built_in_database/rules/users/{username}"
        response = self._request("GET", endpoint)

        return self._handle_response(response)

    def create_user_authorization_rules_built_in_database(self, username, rules: dict) -> Union[str, list, dict]:
        endpoint = f"/authorization/sources/built_in_database/rules/users/{username}"
        response = self._request("PUT", endpoint, data=rules)

        return self._handle_response(response)

    def delete_user_authorization_rules_built_in_database(self, username) -> Union[str, list, dict]:
        endpoint = f"/authorization/sources/built_in_database/rules/users/{username}"
        response = self._request("DELETE", endpoint)

        return self._handle_response(response)
