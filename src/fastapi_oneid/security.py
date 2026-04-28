from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Protocol
from urllib.parse import urlparse

from .exceptions import OneIDInvalidRedirectURIError, OneIDInvalidStateError


class StateStore(Protocol):
    async def store(self, state: str, redirect_uri: str, ttl: int) -> None:
        """Persist a state token with its redirect URI."""

    async def pop(self, state: str) -> str | None:
        """Consume a stored state token and return its redirect URI."""


@dataclass(slots=True)
class _StoredState:
    redirect_uri: str
    expires_at: float


class InMemoryStateStore:
    def __init__(self) -> None:
        self._states: dict[str, _StoredState] = {}
        self._lock = asyncio.Lock()

    async def store(self, state: str, redirect_uri: str, ttl: int) -> None:
        async with self._lock:
            self._cleanup_unlocked()
            self._states[state] = _StoredState(
                redirect_uri=redirect_uri,
                expires_at=time.monotonic() + ttl,
            )

    async def pop(self, state: str) -> str | None:
        async with self._lock:
            self._cleanup_unlocked()
            stored = self._states.pop(state, None)
            if stored is None:
                return None
            return stored.redirect_uri

    def _cleanup_unlocked(self) -> None:
        now = time.monotonic()
        expired = [key for key, value in self._states.items() if value.expires_at <= now]
        for key in expired:
            self._states.pop(key, None)


def generate_state(length: int = 32) -> str:
    return token_urlsafe(length)


def validate_redirect_uri(redirect_uri: str, allowed_redirect_uris: list[str]) -> str:
    value = redirect_uri.strip()
    if not value:
        raise OneIDInvalidRedirectURIError("Redirect URI must not be empty")

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OneIDInvalidRedirectURIError("Redirect URI must be an absolute HTTP(S) URL")

    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        raise OneIDInvalidRedirectURIError("Loopback redirect URIs are not allowed by OneID")

    if value not in allowed_redirect_uris:
        raise OneIDInvalidRedirectURIError("Redirect URI is not present in ONE_ID_ALLOWED_REDIRECT_URIS")

    return value


async def store_state(state_store: StateStore, state: str, redirect_uri: str, ttl: int) -> None:
    await state_store.store(state=state, redirect_uri=redirect_uri, ttl=ttl)


async def verify_state(
    state_store: StateStore,
    state: str,
    redirect_uri: str | None = None,
) -> str:
    stored_redirect_uri = await state_store.pop(state)
    if stored_redirect_uri is None:
        raise OneIDInvalidStateError("State is invalid or expired")

    if redirect_uri is not None and redirect_uri != stored_redirect_uri:
        raise OneIDInvalidRedirectURIError("Redirect URI does not match the stored state")

    return stored_redirect_uri
