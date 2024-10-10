import pytest
import requests

from bridger.emqx.authorization import AuthorizationMixin


@pytest.fixture
def authz_mixin():
    class Client(AuthorizationMixin):
        def _request(self, method, endpoint, data=None, params=None) -> requests.Response:
            url = f"http://localhost:18083{endpoint}"
            return requests.request(method, url, json=data, params=params)

        def _handle_response(self, response):
            if response.status_code in [200, 201]:
                return response.json()
            return response.text

    return Client()


def test_get_user_authorization_rules_built_in_database(authz_mixin, requests_mock):
    requests_mock.get(
        "http://localhost:18083/authorization/sources/built_in_database/rules/users/user1",
        json={"rules": ["rule1", "rule2"]},
    )
    response = authz_mixin.get_user_authorization_rules_built_in_database("user1")
    assert response == {"rules": ["rule1", "rule2"]}


def test_create_user_authorization_rules_built_in_database(authz_mixin, requests_mock):
    requests_mock.put(
        "http://localhost:18083/authorization/sources/built_in_database/rules/users/user1", json={"result": "created"}
    )
    response = authz_mixin.create_user_authorization_rules_built_in_database("user1", [{"rule": "rule1"}])
    assert response == {"result": "created"}


def test_delete_user_authorization_rules_built_in_database(authz_mixin, requests_mock):
    requests_mock.delete(
        "http://localhost:18083/authorization/sources/built_in_database/rules/users/user1",
        text="Deleted",
        status_code=204,
    )
    response = authz_mixin.delete_user_authorization_rules_built_in_database("user1")
    assert response == "Deleted"
