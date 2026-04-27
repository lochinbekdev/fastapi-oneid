from typing import Any

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    redirect_url: str | None = None


class AccessRequest(BaseModel):
    code: str
    redirect_url: str | None = None


class AuthorizationUrlResponse(BaseModel):
    url: str


class OneIDAuthPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: str
    redirect_url: str
    token: dict[str, Any]
    user: dict[str, Any]
