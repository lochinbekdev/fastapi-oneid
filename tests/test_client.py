from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from fastapi_oneid.client import OneIDClient
from fastapi_oneid.exceptions import OneIDTokenError, OneIDUpstreamError
from fastapi_oneid.settings import OneIDSettings


@pytest.fixture
def settings() -> OneIDSettings:
    return OneIDSettings(
        one_id_sso_url="https://sso.example.com/api/oauth2",
        one_id_client_id="client-id",
        one_id_client_secret="client-secret",
        one_id_client_scope="test-scope",
        one_id_client_state="state-1",
    )


def test_get_authorization_url(settings: OneIDSettings) -> None:
    client = OneIDClient(settings=settings, http_client=httpx.AsyncClient())

    url = client.get_authorization_url("https://app.example.com/callback")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert params["response_type"] == ["one_code"]
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://app.example.com/callback"]
    assert params["scope"] == ["test-scope"]
    assert params["state"] == ["state-1"]


@pytest.mark.asyncio
@respx.mock
async def test_resolve_auth_payload(settings: OneIDSettings) -> None:
    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc"}),
        httpx.Response(200, json={"pin": "123456789", "name": "Ali"}),
    ]
    client = OneIDClient(settings=settings)

    payload = await client.resolve_auth_payload(
        code="code-1",
        redirect_url="https://app.example.com/callback",
    )

    assert payload.token["access_token"] == "abc"
    assert payload.user["pin"] == "123456789"
    assert route.calls[0].request.content.decode() == (
        "grant_type=one_authorization_code&client_id=client-id&"
        "client_secret=client-secret&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&code=code-1"
    )
    assert route.calls[1].request.content.decode() == (
        "grant_type=one_access_token_identify&client_id=client-id&"
        "client_secret=client-secret&access_token=abc&scope=test-scope"
    )
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_missing_access_token_raises(settings: OneIDSettings) -> None:
    respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(200, json={"error": "bad"}))
    client = OneIDClient(settings=settings)

    with pytest.raises(OneIDTokenError):
        await client.resolve_auth_payload(code="code-1", redirect_url="https://app.example.com/callback")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_upstream_http_error_raises(settings: OneIDSettings) -> None:
    respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(500, text="boom"))
    client = OneIDClient(settings=settings)

    with pytest.raises(OneIDUpstreamError):
        await client.exchange_code("code-1", "https://app.example.com/callback")

    await client.aclose()
