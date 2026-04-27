from __future__ import annotations

from contextlib import asynccontextmanager
import inspect
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from .client import OneIDClient
from .exceptions import OneIDError, OneIDTokenError, OneIDUpstreamError
from .handlers import HandlerResult, OneIDAuthHandler
from .schemas import AccessRequest, AuthorizationUrlResponse, LoginRequest
from .settings import OneIDSettings


def create_web_router(
    *,
    settings: OneIDSettings | None = None,
    client: OneIDClient | None = None,
    handler: OneIDAuthHandler | None = None,
    prefix: str = "/one-id",
) -> APIRouter:
    one_id_client = client or OneIDClient(settings=settings)
    router = APIRouter(prefix=prefix, tags=["one-id"], lifespan=_lifespan(one_id_client))

    @router.get("/login", name="one-id.login")
    async def login(request: Request) -> RedirectResponse:
        payload = await _parse_login_request(request)
        redirect_url = payload.redirect_url or str(request.url_for("one-id.access"))
        url = one_id_client.get_authorization_url(redirect_url)
        return RedirectResponse(url=url)

    @router.get("/access", name="one-id.access")
    async def access(request: Request) -> Response:
        payload = await _parse_access_request(request)
        redirect_url = payload.redirect_url or str(request.url_for("one-id.access"))
        auth_payload = await _resolve_payload(one_id_client, payload.code, redirect_url)
        return await _build_handler_response(auth_payload, request, handler)

    return router


def create_api_router(
    *,
    settings: OneIDSettings | None = None,
    client: OneIDClient | None = None,
    handler: OneIDAuthHandler | None = None,
    prefix: str = "/api/one-id",
) -> APIRouter:
    one_id_client = client or OneIDClient(settings=settings)
    router = APIRouter(prefix=prefix, tags=["one-id"], lifespan=_lifespan(one_id_client))

    @router.get("/url", name="one-id.url", response_model=AuthorizationUrlResponse)
    async def get_url(request: Request) -> AuthorizationUrlResponse:
        payload = await _parse_login_request(request)
        redirect_url = payload.redirect_url or str(request.url_for("one-id.access-code"))
        url = one_id_client.get_authorization_url(redirect_url)
        return AuthorizationUrlResponse(url=url)

    @router.post("/url", name="one-id.url.post", response_model=AuthorizationUrlResponse)
    async def post_url(request: Request) -> AuthorizationUrlResponse:
        payload = await _parse_login_request(request)
        redirect_url = payload.redirect_url or str(request.url_for("one-id.access-code"))
        url = one_id_client.get_authorization_url(redirect_url)
        return AuthorizationUrlResponse(url=url)

    @router.post("/token", name="one-id.token")
    async def token(request: Request) -> Response:
        payload = await _parse_access_request(request)
        redirect_url = payload.redirect_url or str(request.url_for("one-id.access-code"))
        auth_payload = await _resolve_payload(one_id_client, payload.code, redirect_url)
        return await _build_handler_response(auth_payload, request, handler)

    @router.get("/access", name="one-id.access-code")
    async def access(request: Request) -> dict[str, str]:
        payload = await _parse_access_request(request)
        return {"code": payload.code}

    return router


async def _parse_login_request(request: Request) -> LoginRequest:
    return await _parse_request_model(request, LoginRequest)


async def _parse_access_request(request: Request) -> AccessRequest:
    return await _parse_request_model(request, AccessRequest)


async def _parse_request_model(request: Request, model_type: type[LoginRequest | AccessRequest]):
    data = dict(request.query_params)
    data.update(await _read_request_body(request))
    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


async def _read_request_body(request: Request) -> dict[str, Any]:
    if request.method not in {"POST", "PUT", "PATCH"}:
        return {}

    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = await request.json()
        except JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    if content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        form = await request.form()
        return dict(form)

    return {}


async def _resolve_payload(client: OneIDClient, code: str, redirect_url: str):
    try:
        return await client.resolve_auth_payload(code=code, redirect_url=redirect_url)
    except OneIDTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OneIDUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OneIDError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _build_handler_response(
    auth_payload,
    request: Request,
    handler: OneIDAuthHandler | None,
) -> Response:
    if handler is None:
        return JSONResponse({"token": auth_payload.token, "user": auth_payload.user})

    result: HandlerResult | Any = handler(auth_payload, request)
    if inspect.isawaitable(result):
        result = await result

    if isinstance(result, Response):
        return result

    return JSONResponse(content=result)


def _lifespan(client: OneIDClient):
    @asynccontextmanager
    async def lifespan(_: Any):
        try:
            yield
        finally:
            await client.aclose()

    return lifespan
