class AuthenticationMixin:
    def list_users(self, authentication_id):
        endpoint = f"/authentication/{authentication_id}/users"
        response = self._request("GET", endpoint)
        return self._handle_response(response)

    def get_user(self, authentication_id, user_id):
        endpoint = f"/authentication/{authentication_id}/users/{user_id}"
        return self._request("GET", endpoint)

    def create_user(self, authentication_id, user_id, password, is_superuser=False):
        endpoint = f"/authentication/{authentication_id}/users"
        data = {"user_id": user_id, "password": password, "is_superuser": is_superuser}
        request = self._request("POST", endpoint, data=data)
        return self._handle_response(request)

    def list_authentication(self):
        endpoint = "/authentication"
        request = self._request("GET", endpoint)
        return self._handle_response(request)

    def get_authentication(self, authentication_id):
        endpoint = f"/authentication/{authentication_id}"
        request = self._request("GET", endpoint)
        return self._handle_response(request)

    def delete_user(self, authentication_id, user_id):
        endpoint = f"/authentication/{authentication_id}/users/{user_id}"
        request = self._request("DELETE", endpoint)
        return self._handle_response(request)

    def update_user_password(self, authentication_id, user_id, password):
        endpoint = f"/authentication/{authentication_id}/users/{user_id}"
        data = {"password": password}
        request = self._request("PUT", endpoint, data=data)
        return self._handle_response(request)
