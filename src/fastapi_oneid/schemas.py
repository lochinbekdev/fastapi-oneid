from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False

    raise ValueError("Value must be a boolean or boolean-like string")


class LoginRequest(BaseModel):
    redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("redirect_uri", "redirect_url"),
    )


class TokenRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("redirect_uri", "redirect_url"),
    )


class AccessCallbackResponse(BaseModel):
    code: str
    state: str


class LogoutRequest(BaseModel):
    access_token: str


class AuthorizationUrlResponse(BaseModel):
    url: str


class OneIDTokenResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    access_token: str
    scope: str | None = None
    expires_in: int | None = None
    token_type: str | None = None
    refresh_token: str | None = None


class OneIDLegalInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    is_basic: bool | None = None
    tin: str | None = None
    le_tin: str | None = None
    acron_UZ: str | None = None
    le_name: str | None = None

    @field_validator("is_basic", mode="before")
    @classmethod
    def _parse_is_basic(cls, value: Any) -> bool | None:
        if value is None:
            return None
        return _normalize_bool(value)


class OneIDUserInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    valid: bool
    validation_method: list[str] | None = None
    pin: str
    user_id: str
    full_name: str
    pport_no: str
    birth_date: str
    sur_name: str
    first_name: str
    mid_name: str
    user_type: str
    sess_id: str
    ret_cd: str
    auth_method: str
    pkcs_legal_tin: str | None = None
    legal_info: list[OneIDLegalInfo] | None = None

    @field_validator("valid", mode="before")
    @classmethod
    def _parse_valid(cls, value: Any) -> bool:
        return _normalize_bool(value)

    @field_validator("validation_method", mode="before")
    @classmethod
    def _parse_validation_method(cls, value: Any) -> list[str] | None:
        if value in (None, "", []):
            return None

        if isinstance(value, str):
            return [value]

        if isinstance(value, list):
            return [str(item) for item in value]

        raise ValueError("validation_method must be a string, list, or null")

    @field_validator("legal_info", mode="before")
    @classmethod
    def _parse_legal_info(cls, value: Any) -> list[dict[str, Any]] | None:
        if value in (None, "", []):
            return None

        if isinstance(value, dict):
            return [value]

        if isinstance(value, list):
            return value

        raise ValueError("legal_info must be an object, list, or null")


class OneIDAuthPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: str
    redirect_uri: str
    token: OneIDTokenResponse
    user: OneIDUserInfo

    @property
    def redirect_url(self) -> str:
        return self.redirect_uri


class OneIDLogoutResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    ret_cd: str | None = None
