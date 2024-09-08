class ApiMixin:
    def list_api_keys(self):
        endpoint = "/api_key"
        return self._request("GET", endpoint)

    def create_api_key(self, key_name, secret, role="administrator"):
        endpoint = "/api_key"
        data = {"key_name": key_name, "secret": secret, "role": role}
        return self._request("POST", endpoint, data=data)

    def get_api_key(self, key_id):
        endpoint = f"/api_key/{key_id}"
        return self._request("GET", endpoint)

    def update_api_key(self, key_id, key_name, secret, role):
        endpoint = f"/api_key/{key_id}"
        data = {"key_name": key_name, "secret": secret, "role": role}
        return self._request("PUT", endpoint, data=data)

    def delete_api_key(self, key_id):
        endpoint = f"/api_key/{key_id}"
        return self._request("DELETE", endpoint)
