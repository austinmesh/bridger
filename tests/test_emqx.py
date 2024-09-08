import pytest
import requests
from requests.auth import HTTPBasicAuth

from bridger.emqx import EMQXClient


@pytest.fixture
def emqx_client():
    return EMQXClient(base_url="http://localhost:18083", api_key="api_key", secret_key="secret_key")


def test_emqx_client_initialization(emqx_client):
    assert emqx_client.base_url == "http://localhost:18083"
    assert emqx_client.prefix == "/api/v5"
    assert isinstance(emqx_client.auth, HTTPBasicAuth)


def test_request_success(requests_mock, emqx_client):
    # Mocking the request
    requests_mock.get("http://localhost:18083/api/v5/test-endpoint", json={"key": "value"}, status_code=200)

    response = emqx_client._request("GET", "/test-endpoint")
    assert response.status_code == 200
    assert response.json() == {"key": "value"}


def test_request_with_params(requests_mock, emqx_client):
    # Mocking a GET request with query parameters
    requests_mock.get("http://localhost:18083/api/v5/test-endpoint", json={"key": "value"}, status_code=200)

    response = emqx_client._request("GET", "/test-endpoint", params={"param": "value"})
    assert response.status_code == 200
    assert response.json() == {"key": "value"}


def test_handle_response_json(emqx_client):
    # Mock response with JSON data
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"key": "value"}'

    parsed_response = emqx_client._handle_response(response)
    assert parsed_response == {"key": "value"}


def test_handle_response_text(emqx_client):
    # Mock response with plain text
    response = requests.Response()
    response.status_code = 204
    response._content = b"Success"

    parsed_response = emqx_client._handle_response(response)
    assert parsed_response == "Success"


def test_handle_response_error(emqx_client):
    # Mock error response
    response = requests.Response()
    response.status_code = 404
    response._content = b'{"error": "not found"}'

    with pytest.raises(requests.exceptions.HTTPError):
        emqx_client._handle_response(response)


def test_request_post(requests_mock, emqx_client):
    # Mocking a POST request
    requests_mock.post("http://localhost:18083/api/v5/test-endpoint", json={"result": "created"}, status_code=201)

    response = emqx_client._request("POST", "/test-endpoint", data={"key": "value"})
    assert response.status_code == 201
    assert response.json() == {"result": "created"}


def test_request_raises_exception(requests_mock, emqx_client):
    # Mocking a request that raises an exception
    requests_mock.get("http://localhost:18083/api/v5/test-endpoint", status_code=500)

    with pytest.raises(requests.exceptions.HTTPError):
        response = emqx_client._request("GET", "/test-endpoint")
        emqx_client._handle_response(response)
