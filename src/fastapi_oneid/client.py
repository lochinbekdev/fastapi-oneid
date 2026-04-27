from __future__ import annotations

from json import JSONDecodeError
from urllib.parse import urlencode

import httpx

from .constants import (
    GRANT_TYPE_ACCESS_TOKEN_IDENTIFY,
    GRANT_TYPE_AUTHORIZATION_CODE,
    RESPONSE_TYPE,
)
from .exceptions import OneIDTokenError, OneIDUpstreamError
from .schemas import OneIDAuthPayload
from .settings import OneIDSettings


class OneIDClient:
    def __init__(
        self,
        settings: OneIDSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or OneIDSettings()
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.http_client.aclose()

    def get_authorization_url(
        self,
        redirect_url: str,
        scope: str | None = None,
        state: str | None = None,
    ) -> str:
        params = urlencode(
            {
                "response_type": RESPONSE_TYPE,
                "client_id": self.settings.one_id_client_id,
                "redirect_uri": redirect_url,
                "scope": scope or self.settings.one_id_client_scope,
                "state": state or self.settings.one_id_client_state,
            }
        )
        return f"{self.settings.one_id_sso_url}?{params}"

    async def exchange_code(self, code: str, redirect_url: str) -> dict:
        return await self._post_form(
            {
                "grant_type": GRANT_TYPE_AUTHORIZATION_CODE,
                "client_id": self.settings.one_id_client_id,
                "client_secret": self.settings.one_id_client_secret,
                "redirect_uri": redirect_url,
                "code": code,
            }
        )

    async def get_user_info(self, access_token: str, scope: str | None = None) -> dict:
        return await self._post_form(
            {
                "grant_type": GRANT_TYPE_ACCESS_TOKEN_IDENTIFY,
                "client_id": self.settings.one_id_client_id,
                "client_secret": self.settings.one_id_client_secret,
                "access_token": access_token,
                "scope": scope or self.settings.one_id_client_scope,
            }
        )

    async def get_user(self, code: str, redirect_url: str) -> dict:
        payload = await self.resolve_auth_payload(code=code, redirect_url=redirect_url)
        return payload.user

    async def resolve_auth_payload(self, code: str, redirect_url: str) -> OneIDAuthPayload:
        token = await self.exchange_code(code=code, redirect_url=redirect_url)
        access_token = token.get("access_token")
        if not access_token:
            raise OneIDTokenError("Unable to get OneID access token")

        user = await self.get_user_info(access_token=access_token)
        return OneIDAuthPayload(
            code=code,
            redirect_url=redirect_url,
            token=token,
            user=user,
        )

    async def _post_form(self, data: dict[str, str]) -> dict:
        try:
            response = await self.http_client.post(self.settings.one_id_sso_url, data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or exc.response.reason_phrase
            raise OneIDUpstreamError(f"OneID upstream returned {exc.response.status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            raise OneIDUpstreamError(f"OneID upstream request failed: {exc}") from exc

        try:
            return response.json()
        except JSONDecodeError as exc:
            raise OneIDUpstreamError("OneID upstream returned a non-JSON response") from exc
