from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fastapi_oneid import OneIDAuthPayload, create_api_router, create_web_router
from fastapi_oneid.settings import OneIDSettings


def build_user_payload(**overrides) -> dict:
    payload = {
        "valid": "true",
        "validation_method": ["PKCSMETHOD"],
        "pin": "98765432101234",
        "user_id": "oneid-user",
        "full_name": "Vali Karimov",
        "pport_no": "AA7654321",
        "birth_date": "1992-02-02",
        "sur_name": "Karimov",
        "first_name": "Vali",
        "mid_name": "Karim o'g'li",
        "user_type": "I",
        "sess_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "ret_cd": "0",
        "auth_method": "LOGINPASSMETHOD",
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
        one_id_debug=False,
    )


@pytest.fixture
def app(settings: OneIDSettings) -> FastAPI:
    app = FastAPI()
    app.include_router(create_web_router(settings=settings))
    app.include_router(create_api_router(settings=settings))
    return app


def extract_state(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


@pytest.mark.asyncio
async def test_web_login_redirects_with_state(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        response = await client.get("/one-id/login", follow_redirects=False)

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    params = parse_qs(urlparse(location).query)
    assert params["redirect_uri"] == ["https://backend.example.com/one-id/access"]
    assert params["state"]


@pytest.mark.asyncio
async def test_api_url_returns_whitelisted_authorization_url(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        response = await client.get("/api/one-id/url?redirect_uri=https://frontend.example.com/callback")

    assert response.status_code == 200
    params = parse_qs(urlparse(response.json()["url"]).query)
    assert params["redirect_uri"] == ["https://frontend.example.com/callback"]
    assert params["response_type"] == ["one_code"]
    assert params["state"]


@pytest.mark.asyncio
async def test_api_access_echoes_code_and_state(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        response = await client.get("/api/one-id/access?code=code-1&state=state-1")

    assert response.status_code == 200
    assert response.json() == {"code": "code-1", "state": "state-1"}


@pytest.mark.asyncio
async def test_invalid_redirect_uri_is_rejected(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        response = await client.get("/api/one-id/url?redirect_uri=https://evil.example.com/callback")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_invalid_state_is_rejected(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        response = await client.post(
            "/api/one-id/token",
            json={
                "code": "code-1",
                "state": "missing-state",
                "redirect_uri": "https://frontend.example.com/callback",
            },
        )

    assert response.status_code == 400
    assert "State" in response.json()["detail"]


@pytest.mark.asyncio
async def test_redirect_uri_mismatch_is_rejected(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        url_response = await client.get("/api/one-id/url?redirect_uri=https://frontend.example.com/callback")
        state = extract_state(url_response.json()["url"])
        response = await client.post(
            "/api/one-id/token",
            json={
                "code": "code-1",
                "state": state,
                "redirect_uri": "https://backend.example.com/one-id/access",
            },
        )

    assert response.status_code == 400
    assert "Redirect URI does not match" in response.json()["detail"]


@pytest.mark.asyncio
@respx.mock
async def test_handler_is_called_with_typed_payload(settings: OneIDSettings) -> None:
    async def handler(payload: OneIDAuthPayload, request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "project_token": "jwt",
                "pin": payload.user.pin,
                "valid": payload.user.valid,
                "redirect_uri": payload.redirect_uri,
            }
        )

    app = FastAPI()
    app.include_router(create_api_router(settings=settings, handler=handler))

    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"}),
        httpx.Response(200, json=build_user_payload(valid="true")),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        url_response = await client.get("/api/one-id/url?redirect_uri=https://frontend.example.com/callback")
        state = extract_state(url_response.json()["url"])
        response = await client.post(
            "/api/one-id/token",
            json={
                "code": "code-1",
                "state": state,
                "redirect_uri": "https://frontend.example.com/callback",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "project_token": "jwt",
        "pin": "98765432101234",
        "valid": True,
        "redirect_uri": "https://frontend.example.com/callback",
    }


@pytest.mark.asyncio
@respx.mock
async def test_handler_missing_and_debug_false_does_not_return_raw_payload(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings))

    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"}),
        httpx.Response(200, json=build_user_payload()),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        url_response = await client.get("/api/one-id/url?redirect_uri=https://frontend.example.com/callback")
        state = extract_state(url_response.json()["url"])
        response = await client.post(
            "/api/one-id/token",
            json={
                "code": "code-1",
                "state": state,
                "redirect_uri": "https://frontend.example.com/callback",
            },
        )

    assert response.status_code == 500
    assert "handler" in response.json()["detail"]
    assert "token" not in response.text


@pytest.mark.asyncio
@respx.mock
async def test_debug_mode_allows_raw_payload(settings: OneIDSettings) -> None:
    debug_settings = settings.model_copy(update={"one_id_debug": True})
    app = FastAPI()
    app.include_router(create_api_router(settings=debug_settings))

    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"}),
        httpx.Response(200, json=build_user_payload()),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        url_response = await client.get("/api/one-id/url")
        state = extract_state(url_response.json()["url"])
        response = await client.post(
            "/api/one-id/token",
            json={
                "code": "code-1",
                "state": state,
            },
        )

    assert response.status_code == 200
    assert response.json()["token"]["access_token"] == "abc"
    assert response.json()["user"]["pin"] == "98765432101234"


@pytest.mark.asyncio
@respx.mock
async def test_ret_cd_not_zero_maps_to_401(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings, handler=lambda payload, request: {"ok": True}))

    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc", "token_type": "bearer"}),
        httpx.Response(200, json=build_user_payload(ret_cd="1")),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        url_response = await client.get("/api/one-id/url")
        state = extract_state(url_response.json()["url"])
        response = await client.post("/api/one-id/token", json={"code": "code-1", "state": state})

    assert response.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_logout_endpoint_calls_client_logout(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings))
    route = respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(200, json={"ret_cd": "0"}))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        response = await client.post("/api/one-id/logout", json={"access_token": "abc"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "grant_type=one_log_out" in route.calls[0].request.content.decode()


@pytest.mark.asyncio
@respx.mock
async def test_upstream_error_maps_to_502(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings, handler=lambda payload, request: {"ok": True}))
    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [httpx.Response(500, text="boom")]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://backend.example.com") as client:
        url_response = await client.get("/api/one-id/url")
        state = extract_state(url_response.json()["url"])
        response = await client.post("/api/one-id/token", json={"code": "code-1", "state": state})

    assert response.status_code == 502
