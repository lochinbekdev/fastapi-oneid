import httpx
import pytest
import respx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fastapi_oneid import OneIDAuthPayload, create_api_router, create_web_router
from fastapi_oneid.settings import OneIDSettings


@pytest.fixture
def settings() -> OneIDSettings:
    return OneIDSettings(
        one_id_sso_url="https://sso.example.com/api/oauth2",
        one_id_client_id="client-id",
        one_id_client_secret="client-secret",
    )


@pytest.fixture
def app(settings: OneIDSettings) -> FastAPI:
    app = FastAPI()
    app.include_router(create_web_router(settings=settings))
    app.include_router(create_api_router(settings=settings))
    return app


@pytest.mark.asyncio
async def test_web_login_redirects_to_oneid(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://local.test") as client:
        response = await client.get("/one-id/login", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"].startswith("https://sso.example.com/api/oauth2?")
    assert "redirect_uri=https%3A%2F%2Flocal.test%2Fone-id%2Faccess" in response.headers["location"]


@pytest.mark.asyncio
async def test_api_url_uses_default_callback(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://local.test") as client:
        response = await client.get("/api/one-id/url")

    assert response.status_code == 200
    assert response.json()["url"].startswith("https://sso.example.com/api/oauth2?")
    assert "redirect_uri=https%3A%2F%2Flocal.test%2Fapi%2Fone-id%2Faccess" in response.json()["url"]


@pytest.mark.asyncio
@respx.mock
async def test_api_token_returns_raw_payload(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings))

    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc"}),
        httpx.Response(200, json={"pin": "987654321", "name": "Vali"}),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://local.test") as client:
        response = await client.post("/api/one-id/token", json={"code": "code-1"})

    assert response.status_code == 200
    assert response.json()["token"]["access_token"] == "abc"
    assert response.json()["user"]["pin"] == "987654321"


@pytest.mark.asyncio
@respx.mock
async def test_handler_response_is_used(settings: OneIDSettings) -> None:
    async def handler(payload: OneIDAuthPayload, request: Request) -> JSONResponse:
        return JSONResponse({"project_token": "jwt", "pin": payload.user["pin"]})

    app = FastAPI()
    app.include_router(create_api_router(settings=settings, handler=handler))

    route = respx.post("https://sso.example.com/api/oauth2")
    route.side_effect = [
        httpx.Response(200, json={"access_token": "abc"}),
        httpx.Response(200, json={"pin": "123123123"}),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://local.test") as client:
        response = await client.post("/api/one-id/token", json={"code": "code-1"})

    assert response.status_code == 200
    assert response.json() == {"project_token": "jwt", "pin": "123123123"}


@pytest.mark.asyncio
@respx.mock
async def test_upstream_error_maps_to_502(settings: OneIDSettings) -> None:
    app = FastAPI()
    app.include_router(create_api_router(settings=settings))
    respx.post("https://sso.example.com/api/oauth2").mock(return_value=httpx.Response(500, text="boom"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://local.test") as client:
        response = await client.post("/api/one-id/token", json={"code": "code-1"})

    assert response.status_code == 502
