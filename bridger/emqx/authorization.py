from typing import Union


class AuthorizationMixin:
    def get_user_authorization_rules_built_in_database(self, username) -> Union[str, list, dict]:
        endpoint = f"/authorization/sources/built_in_database/rules/users/{username}"
        response = self._request("GET", endpoint)

        return self._handle_response(response)

    def create_user_authorization_rules_built_in_database(self, username, rules: list[dict]) -> Union[str, list, dict]:
        endpoint = f"/authorization/sources/built_in_database/rules/users/{username}"
        response = self._request("PUT", endpoint, data=rules)

        return self._handle_response(response)

    def delete_user_authorization_rules_built_in_database(self, username) -> Union[str, list, dict]:
        endpoint = f"/authorization/sources/built_in_database/rules/users/{username}"
        response = self._request("DELETE", endpoint)

        return self._handle_response(response)
