from __future__ import annotations

import json
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import DEFAULT_DEBUG, DEFAULT_STATE_TTL, DEFAULT_TIMEOUT


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False

    host = hostname.lower()
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class OneIDSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    one_id_sso_url: str
    one_id_client_id: str
    one_id_client_secret: str
    one_id_scope: str = Field(validation_alias=AliasChoices("ONE_ID_SCOPE", "ONE_ID_CLIENT_SCOPE"))
    one_id_allowed_redirect_uris: list[str]
    one_id_default_redirect_uri: str
    one_id_timeout: float = DEFAULT_TIMEOUT
    one_id_debug: bool = DEFAULT_DEBUG
    one_id_state_ttl: int = DEFAULT_STATE_TTL

    @field_validator("one_id_sso_url", "one_id_scope", "one_id_default_redirect_uri", mode="before")
    @classmethod
    def _strip_string(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("one_id_allowed_redirect_uris", mode="before")
    @classmethod
    def _parse_allowed_redirect_uris(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]

        if not isinstance(value, str):
            raise TypeError("ONE_ID_ALLOWED_REDIRECT_URIS must be a list or string")

        raw = value.strip()
        if not raw:
            return []

        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("ONE_ID_ALLOWED_REDIRECT_URIS JSON value must be a list")
            return [str(item).strip() for item in parsed if str(item).strip()]

        return [item.strip() for item in raw.split(",") if item.strip()]

    @field_validator("one_id_timeout")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ONE_ID_TIMEOUT must be greater than zero")
        return value

    @field_validator("one_id_state_ttl")
    @classmethod
    def _validate_state_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ONE_ID_STATE_TTL must be greater than zero")
        return value

    @model_validator(mode="after")
    def _validate_redirect_settings(self) -> "OneIDSettings":
        if not self.one_id_allowed_redirect_uris:
            raise ValueError("ONE_ID_ALLOWED_REDIRECT_URIS must contain at least one redirect URI")

        allowed = {uri.strip() for uri in self.one_id_allowed_redirect_uris if uri.strip()}
        if self.one_id_default_redirect_uri not in allowed:
            raise ValueError("ONE_ID_DEFAULT_REDIRECT_URI must be included in ONE_ID_ALLOWED_REDIRECT_URIS")

        for redirect_uri in allowed:
            parsed = urlparse(redirect_uri)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid redirect URI: {redirect_uri}")
            if _is_loopback_host(parsed.hostname):
                raise ValueError(f"Loopback redirect URI is not allowed: {redirect_uri}")

        parsed_sso = urlparse(self.one_id_sso_url)
        if parsed_sso.scheme not in {"http", "https"} or not parsed_sso.netloc:
            raise ValueError("ONE_ID_SSO_URL must be a valid absolute URL")

        return self
