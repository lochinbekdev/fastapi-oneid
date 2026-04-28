from __future__ import annotations

from contextlib import asynccontextmanager
import inspect
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from .client import OneIDClient
from .exceptions import (
    OneIDError,
    OneIDHTTPError,
    OneIDInvalidRedirectURIError,
    OneIDInvalidStateError,
    OneIDLogoutError,
    OneIDTokenExchangeError,
    OneIDUserInfoError,
)
from .handlers import HandlerResult, OneIDAuthHandler
from .schemas import (
    AccessCallbackResponse,
    AuthorizationUrlResponse,
    LoginRequest,
    LogoutRequest,
    TokenRequest,
)
from .security import InMemoryStateStore, StateStore, generate_state, store_state, validate_redirect_uri, verify_state
from .settings import OneIDSettings


def create_web_router(
    *,
    settings: OneIDSettings | None = None,
    client: OneIDClient | None = None,
    handler: OneIDAuthHandler | None = None,
    state_store: StateStore | None = None,
    prefix: str = "/one-id",
) -> APIRouter:
    one_id_client = client or OneIDClient(settings=settings)
    one_id_settings = one_id_client.settings
    active_state_store = state_store or InMemoryStateStore()
    router = APIRouter(prefix=prefix, tags=["one-id"], lifespan=_lifespan(one_id_client))

    @router.get("/login", name="one-id.login")
    async def login(request: Request) -> RedirectResponse:
        payload = await _parse_request_model(request, LoginRequest)
        try:
            redirect_uri = _resolve_redirect_uri(payload.redirect_uri, one_id_settings)
            state = generate_state()
            await store_state(
                active_state_store,
                state=state,
                redirect_uri=redirect_uri,
                ttl=one_id_settings.one_id_state_ttl,
            )
            url = one_id_client.get_authorization_url(redirect_uri, state)
        except Exception as exc:
            raise _map_exception(exc) from exc
        return RedirectResponse(url=url)

    @router.get("/access", name="one-id.access")
    async def access(request: Request) -> Response:
        payload = await _parse_request_model(request, TokenRequest)
        try:
            supplied_redirect_uri = _validate_optional_redirect_uri(payload.redirect_uri, one_id_settings)
            redirect_uri = await verify_state(active_state_store, payload.state, supplied_redirect_uri)
            auth_payload = await one_id_client.resolve_auth_payload(
                code=payload.code,
                redirect_uri=redirect_uri,
            )
        except Exception as exc:
            raise _map_exception(exc) from exc

        return await _build_handler_response(auth_payload, request, handler, one_id_settings)

    return router


def create_api_router(
    *,
    settings: OneIDSettings | None = None,
    client: OneIDClient | None = None,
    handler: OneIDAuthHandler | None = None,
    state_store: StateStore | None = None,
    prefix: str = "/api/one-id",
) -> APIRouter:
    one_id_client = client or OneIDClient(settings=settings)
    one_id_settings = one_id_client.settings
    active_state_store = state_store or InMemoryStateStore()
    router = APIRouter(prefix=prefix, tags=["one-id"], lifespan=_lifespan(one_id_client))

    @router.get("/url", name="one-id.url", response_model=AuthorizationUrlResponse)
    async def get_url(request: Request) -> AuthorizationUrlResponse:
        payload = await _parse_request_model(request, LoginRequest)
        try:
            redirect_uri = _resolve_redirect_uri(payload.redirect_uri, one_id_settings)
            state = generate_state()
            await store_state(
                active_state_store,
                state=state,
                redirect_uri=redirect_uri,
                ttl=one_id_settings.one_id_state_ttl,
            )
            url = one_id_client.get_authorization_url(redirect_uri, state)
        except Exception as exc:
            raise _map_exception(exc) from exc
        return AuthorizationUrlResponse(url=url)

    @router.post("/url", name="one-id.url.post", response_model=AuthorizationUrlResponse)
    async def post_url(request: Request) -> AuthorizationUrlResponse:
        payload = await _parse_request_model(request, LoginRequest)
        try:
            redirect_uri = _resolve_redirect_uri(payload.redirect_uri, one_id_settings)
            state = generate_state()
            await store_state(
                active_state_store,
                state=state,
                redirect_uri=redirect_uri,
                ttl=one_id_settings.one_id_state_ttl,
            )
            url = one_id_client.get_authorization_url(redirect_uri, state)
        except Exception as exc:
            raise _map_exception(exc) from exc
        return AuthorizationUrlResponse(url=url)

    @router.post("/token", name="one-id.token")
    async def token(request: Request) -> Response:
        payload = await _parse_request_model(request, TokenRequest)
        try:
            supplied_redirect_uri = _validate_optional_redirect_uri(payload.redirect_uri, one_id_settings)
            redirect_uri = await verify_state(active_state_store, payload.state, supplied_redirect_uri)
            auth_payload = await one_id_client.resolve_auth_payload(
                code=payload.code,
                redirect_uri=redirect_uri,
            )
        except Exception as exc:
            raise _map_exception(exc) from exc

        return await _build_handler_response(auth_payload, request, handler, one_id_settings)

    @router.get("/access", name="one-id.access-code", response_model=AccessCallbackResponse)
    async def access(request: Request) -> AccessCallbackResponse:
        payload = await _parse_request_model(request, TokenRequest)
        return AccessCallbackResponse(code=payload.code, state=payload.state)

    @router.post("/logout", name="one-id.logout")
    async def logout(request: Request) -> JSONResponse:
        payload = await _parse_request_model(request, LogoutRequest)
        try:
            response = await one_id_client.logout(payload.access_token)
        except Exception as exc:
            raise _map_exception(exc) from exc

        return JSONResponse(content=response.model_dump())

    return router


async def _parse_request_model(request: Request, model_type: type[Any]):
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


def _resolve_redirect_uri(redirect_uri: str | None, settings: OneIDSettings) -> str:
    candidate = redirect_uri or settings.one_id_default_redirect_uri
    return validate_redirect_uri(candidate, settings.one_id_allowed_redirect_uris)


def _validate_optional_redirect_uri(redirect_uri: str | None, settings: OneIDSettings) -> str | None:
    if redirect_uri is None:
        return None
    return validate_redirect_uri(redirect_uri, settings.one_id_allowed_redirect_uris)


async def _build_handler_response(
    auth_payload,
    request: Request,
    handler: OneIDAuthHandler | None,
    settings: OneIDSettings,
) -> Response:
    if handler is None:
        if not settings.one_id_debug:
            raise HTTPException(status_code=500, detail="OneID handler is not configured")

        return JSONResponse(
            {
                "token": auth_payload.token.model_dump(),
                "user": auth_payload.user.model_dump(),
            }
        )

    result: HandlerResult | Any = handler(auth_payload, request)
    if inspect.isawaitable(result):
        result = await result

    if isinstance(result, Response):
        return result

    return JSONResponse(content=result)


def _map_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, OneIDInvalidStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, OneIDInvalidRedirectURIError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, OneIDTokenExchangeError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, OneIDUserInfoError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, OneIDLogoutError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, OneIDHTTPError):
        status_code = 504 if exc.is_timeout else 502
        return HTTPException(status_code=status_code, detail=str(exc))
    if isinstance(exc, OneIDError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(status_code=500, detail="Unexpected OneID integration error")


def _lifespan(client: OneIDClient):
    @asynccontextmanager
    async def lifespan(_: Any):
        try:
            yield
        finally:
            await client.aclose()

    return lifespan
