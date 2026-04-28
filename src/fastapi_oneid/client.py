from __future__ import annotations

from json import JSONDecodeError
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from .constants import (
    GRANT_TYPE_ACCESS_TOKEN_IDENTIFY,
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_LOGOUT,
    RESPONSE_TYPE,
)
from .exceptions import (
    OneIDHTTPError,
    OneIDLogoutError,
    OneIDTokenExchangeError,
    OneIDUserInfoError,
)
from .schemas import OneIDAuthPayload, OneIDLogoutResponse, OneIDTokenResponse, OneIDUserInfo
from .security import validate_redirect_uri
from .settings import OneIDSettings


class OneIDClient:
    def __init__(
        self,
        settings: OneIDSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or OneIDSettings()
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.AsyncClient(timeout=self.settings.one_id_timeout)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.http_client.aclose()

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        validated_redirect_uri = validate_redirect_uri(
            redirect_uri,
            self.settings.one_id_allowed_redirect_uris,
        )
        params = urlencode(
            {
                "response_type": RESPONSE_TYPE,
                "client_id": self.settings.one_id_client_id,
                "redirect_uri": validated_redirect_uri,
                "scope": self.settings.one_id_scope,
                "state": state,
            }
        )
        return f"{self.settings.one_id_sso_url}?{params}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OneIDTokenResponse:
        validated_redirect_uri = validate_redirect_uri(
            redirect_uri,
            self.settings.one_id_allowed_redirect_uris,
        )
        payload = await self._post_form(
            {
                "grant_type": GRANT_TYPE_AUTHORIZATION_CODE,
                "client_id": self.settings.one_id_client_id,
                "client_secret": self.settings.one_id_client_secret,
                "redirect_uri": validated_redirect_uri,
                "code": code,
            }
        )
        try:
            return OneIDTokenResponse.model_validate(payload)
        except ValidationError as exc:
            raise OneIDTokenExchangeError("OneID token response is missing a valid access_token") from exc

    async def get_user_info(self, access_token: str) -> OneIDUserInfo:
        payload = await self._post_form(
            {
                "grant_type": GRANT_TYPE_ACCESS_TOKEN_IDENTIFY,
                "client_id": self.settings.one_id_client_id,
                "client_secret": self.settings.one_id_client_secret,
                "access_token": access_token,
                "scope": self.settings.one_id_scope,
            }
        )
        try:
            user = OneIDUserInfo.model_validate(payload)
        except ValidationError as exc:
            raise OneIDUserInfoError("OneID user info response is invalid") from exc

        if user.ret_cd != "0":
            raise OneIDUserInfoError(f"OneID user info returned ret_cd={user.ret_cd}")

        return user

    async def resolve_auth_payload(self, code: str, redirect_uri: str) -> OneIDAuthPayload:
        token = await self.exchange_code(code=code, redirect_uri=redirect_uri)
        user = await self.get_user_info(access_token=token.access_token)
        return OneIDAuthPayload(
            code=code,
            redirect_uri=redirect_uri,
            token=token,
            user=user,
        )

    async def get_user(self, code: str, redirect_uri: str) -> OneIDUserInfo:
        payload = await self.resolve_auth_payload(code=code, redirect_uri=redirect_uri)
        return payload.user

    async def logout(self, access_token: str) -> OneIDLogoutResponse:
        payload = await self._post_form(
            {
                "grant_type": GRANT_TYPE_LOGOUT,
                "client_id": self.settings.one_id_client_id,
                "client_secret": self.settings.one_id_client_secret,
                "access_token": access_token,
                "scope": self.settings.one_id_scope,
            }
        )

        ret_cd = payload.get("ret_cd")
        if ret_cd not in (None, "0"):
            raise OneIDLogoutError(f"OneID logout returned ret_cd={ret_cd}")

        try:
            return OneIDLogoutResponse.model_validate(
                {
                    **payload,
                    "success": True,
                    "ret_cd": ret_cd,
                }
            )
        except ValidationError as exc:
            raise OneIDLogoutError("OneID logout response is invalid") from exc

    async def _post_form(self, data: dict[str, str]) -> dict:
        try:
            response = await self.http_client.post(
                self.settings.one_id_sso_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OneIDHTTPError("OneID upstream request timed out", is_timeout=True) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or exc.response.reason_phrase
            raise OneIDHTTPError(
                f"OneID upstream returned {exc.response.status_code}: {detail}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise OneIDHTTPError(f"OneID upstream request failed: {exc}") from exc

        try:
            payload = response.json()
        except JSONDecodeError as exc:
            raise OneIDHTTPError("OneID upstream returned a non-JSON response") from exc

        if not isinstance(payload, dict):
            raise OneIDHTTPError("OneID upstream returned a non-object JSON response")

        return payload
