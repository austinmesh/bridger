import pytest
import requests

from bridger.emqx.authentication import AuthenticationMixin


@pytest.fixture
def auth_mixin():
    class Client(AuthenticationMixin):
        def _request(self, method, endpoint, data=None, params=None) -> requests.Response:
            url = f"http://localhost:18083{endpoint}"
            return requests.request(method, url, json=data, params=params)

        def _handle_response(self, response):
            if response.status_code in [200, 201]:
                return response.json()
            return response.text

    return Client()


def test_list_users(auth_mixin, requests_mock):
    requests_mock.get("http://localhost:18083/authentication/1/users", json=[{"username": "user1"}])
    response = auth_mixin.list_users("1")
    assert response == [{"username": "user1"}]


def test_create_user(auth_mixin, requests_mock):
    # Mock the POST request for creating a user
    requests_mock.post("http://localhost:18083/authentication/1/users", json={"result": "created"}, status_code=201)

    response = auth_mixin.create_user("1", "user1", "password", is_superuser=True)
    last_request = requests_mock.last_request

    assert response == {"result": "created"}
    assert last_request.method == "POST"
    assert last_request.json() == {"password": "password", "is_superuser": True, "user_id": "user1"}


def test_get_authentication(auth_mixin, requests_mock):
    requests_mock.get("http://localhost:18083/authentication/1", json={"mechanism": "password_based"})
    response = auth_mixin.get_authentication("1")
    assert response == {"mechanism": "password_based"}


def test_delete_user(auth_mixin, requests_mock):
    requests_mock.delete("http://localhost:18083/authentication/1/users/user1", text="User deleted", status_code=204)
    response = auth_mixin.delete_user("1", "user1")
    assert response == "User deleted"


def test_update_user_password(auth_mixin, requests_mock):
    requests_mock.put("http://localhost:18083/authentication/1/users/user1", json={"password": "mynewpass"})
    response = auth_mixin.update_user_password("1", "user1", "newpassword")
    assert response == {"password": "mynewpass"}


def test_get_user(auth_mixin, requests_mock):
    requests_mock.get(
        "http://localhost:18083/authentication/1/users/user1", json={"username": "user1", "is_superuser": True}
    )

    response = auth_mixin.get_user("1", "user1")
    assert response.status_code == 200
    assert response.json() == {"username": "user1", "is_superuser": True}


def test_list_authentication(auth_mixin, requests_mock):
    auth_data = [{"mechanism": "password_based", "backend": "built_in_database"}, {"mechanism": "jwt", "secret": "mysecret"}]
    requests_mock.get("http://localhost:18083/authentication", json=auth_data)

    response = auth_mixin.list_authentication()
    assert response == auth_data
