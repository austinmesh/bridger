import pytest
import requests

from bridger.emqx.api import ApiMixin


@pytest.fixture
def api_mixin():
    class Client(ApiMixin):
        def _request(self, method, endpoint, data=None, params=None) -> requests.Response:
            url = f"http://localhost:18083{endpoint}"
            return requests.request(method, url, json=data, params=params)

    return Client()


def test_list_api_keys(api_mixin, requests_mock):
    requests_mock.get("http://localhost:18083/api_key", json=[{"key_name": "mykey", "secret": "secret"}])
    response = api_mixin.list_api_keys()
    assert response.status_code == 200
    assert response.json() == [{"key_name": "mykey", "secret": "secret"}]


def test_create_api_key(api_mixin, requests_mock):
    requests_mock.post("http://localhost:18083/api_key", json={"result": "created"}, status_code=201)
    response = api_mixin.create_api_key("mykey", "secret")
    assert response.status_code == 201
    assert response.json() == {"result": "created"}


def test_get_api_key(api_mixin, requests_mock):
    requests_mock.get("http://localhost:18083/api_key/1", json={"key_name": "mykey", "secret": "secret"})
    response = api_mixin.get_api_key("1")
    assert response.status_code == 200
    assert response.json() == {"key_name": "mykey", "secret": "secret"}


def test_update_api_key(api_mixin, requests_mock):
    requests_mock.put("http://localhost:18083/api_key/1", json={"result": "updated"})
    response = api_mixin.update_api_key("1", "mykey", "newsecret", "administrator")
    assert response.status_code == 200
    assert response.json() == {"result": "updated"}


def test_delete_api_key(api_mixin, requests_mock):
    requests_mock.delete("http://localhost:18083/api_key/1", json={"result": "deleted"}, status_code=204)
    response = api_mixin.delete_api_key("1")
    assert response.status_code == 204
