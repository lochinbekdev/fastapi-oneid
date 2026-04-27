from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response

from .schemas import OneIDAuthPayload

HandlerResult = Response | dict[str, Any]
OneIDAuthHandler = Callable[[OneIDAuthPayload, Request], HandlerResult | Awaitable[HandlerResult]]
