from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from fastapi_oneid.client import OneIDClient
from fastapi_oneid.constants import (
    GRANT_TYPE_ACCESS_TOKEN_IDENTIFY,
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_LOGOUT,
    RESPONSE_TYPE,
)
from fastapi_oneid.exceptions import (
    OneIDHTTPError,
    OneIDInvalidRedirectURIError,
    OneIDLogoutError,
    OneIDTokenExchangeError,
    OneIDUserInfoError,
)
from fastapi_oneid.settings import OneIDSettings


def build_user_payload(**overrides) -> dict:
    payload = {
        "valid": "true",
        "validation_method": ["PKCSMETHOD"],
        "pin": "99999999123456",
        "user_id": "kimdoy",
        "full_name": "Ali Valiyev",
        "pport_no": "AA1234567",
        "birth_date": "1991-01-01",
        "sur_name": "Valiyev",
        "first_name": "Ali",
        "mid_name": "Olimjon o'g'li",
        "user_type": "I",
        "sess_id": "11111111-2222-3333-4444-555555555555",
        "ret_cd": "0",
        "auth_method": "LOGINPASSMETHOD",
        "pkcs_legal_tin": None,
        "legal_info": [],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def settings() -> OneIDSettings:
    return OneIDSettings(
        one_id_sso_url="https://sso.example.com/api/oauth2",
        one_id_client_id="client-id",
        one_id_client_secret="client-secret",
        one_id_scope="myportal",
        one_id_allowed_redirect_uris=[
            "https://backend.example.com/one-id/access",
            "https://frontend.example.com/callback",
        ],
        one_id_default_redirect_uri="https://backend.example.com/one-id/access",
        one_id_timeout=5.0,
    )


def test_get_authorization_url_uses_official_response_type(settings: OneIDSettings) -> None:
    client = OneIDClient(settings=settings, http_client=httpx.AsyncClient())

    url = client.get_authorization_url("https://frontend.example.com/callback", "state-1")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert params["response_type"] == [RESPONSE_TYPE]
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://frontend.example.com/callback"]
    assert params["scope"] == ["myportal"]
    assert params["state"] == ["state-1"]


def test_get_authorization_url_rejects_invalid_redirect_uri(settings: OneIDSettings) -> None:
    client = OneIDClient(settings=settings, http_client=httpx.AsyncClient())

    with pytest.raises(OneIDInvalidRedirectURIError):
        client.get_authorization_url("https://evil.example.com/callback", "state-1")


@pytest.mark.asyncio
@respx.mock
async def test_resolve_auth_payload_uses_official_grant_types(settings: OneIDSettings) -> None:
    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"}),
        httpx.Response(200, json=build_user_payload()),
    ]
    client = OneIDClient(settings=settings)

    payload = await client.resolve_auth_payload(
        code="code-1",
        redirect_uri="https://frontend.example.com/callback",
    )

    assert payload.token.access_token == "abc"
    assert payload.user.pin == "99999999123456"
    assert payload.user.valid is True
    assert route.calls[0].request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert route.calls[0].request.content.decode() == (
        f"grant_type={GRANT_TYPE_AUTHORIZATION_CODE}&client_id=client-id&"
        "client_secret=client-secret&redirect_uri=https%3A%2F%2Ffrontend.example.com%2Fcallback&code=code-1"
    )
    assert route.calls[1].request.content.decode() == (
        f"grant_type={GRANT_TYPE_ACCESS_TOKEN_IDENTIFY}&client_id=client-id&"
        "client_secret=client-secret&access_token=abc&scope=myportal"
    )
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_missing_access_token_raises(settings: OneIDSettings) -> None:
    respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(200, json={"error": "bad"}))
    client = OneIDClient(settings=settings)

    with pytest.raises(OneIDTokenExchangeError):
        await client.exchange_code("code-1", "https://frontend.example.com/callback")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_ret_cd_not_zero_raises(settings: OneIDSettings) -> None:
    respx.post("https://sso.example.com/api/oauth2").mock(
        return_value=httpx.Response(200, json=build_user_payload(ret_cd="1"))
    )
    client = OneIDClient(settings=settings)

    with pytest.raises(OneIDUserInfoError):
        await client.get_user_info("access-token")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_logout_uses_official_grant_type(settings: OneIDSettings) -> None:
    route = respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(200, json={"ret_cd": "0"}))
    client = OneIDClient(settings=settings)

    response = await client.logout("access-token")

    assert response.success is True
    assert route.calls[0].request.content.decode() == (
        f"grant_type={GRANT_TYPE_LOGOUT}&client_id=client-id&"
        "client_secret=client-secret&access_token=access-token&scope=myportal"
    )
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_logout_ret_cd_error_raises(settings: OneIDSettings) -> None:
    respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(200, json={"ret_cd": "1"}))
    client = OneIDClient(settings=settings)

    with pytest.raises(OneIDLogoutError):
        await client.logout("access-token")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_upstream_http_error_raises(settings: OneIDSettings) -> None:
    respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(500, text="boom"))
    client = OneIDClient(settings=settings)

    with pytest.raises(OneIDHTTPError):
        await client.exchange_code("code-1", "https://frontend.example.com/callback")

    await client.aclose()
