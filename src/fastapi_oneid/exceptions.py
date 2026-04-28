class OneIDError(Exception):
    """Base package exception."""


class OneIDHTTPError(OneIDError):
    """Raised when the upstream OneID service fails."""

    def __init__(self, message: str, *, status_code: int | None = None, is_timeout: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.is_timeout = is_timeout


class OneIDInvalidStateError(OneIDError):
    """Raised when the OAuth state is missing, expired, or invalid."""


class OneIDInvalidRedirectURIError(OneIDError):
    """Raised when a redirect URI is not allowed."""


class OneIDTokenExchangeError(OneIDError):
    """Raised when OneID does not return a usable access token."""


class OneIDUserInfoError(OneIDError):
    """Raised when OneID user info response is invalid or unsuccessful."""


class OneIDLogoutError(OneIDError):
    """Raised when OneID logout fails."""


class OneIDTokenError(OneIDTokenExchangeError):
    """Backward-compatible alias for token exchange failures."""


class OneIDUpstreamError(OneIDHTTPError):
    """Backward-compatible alias for upstream OneID failures."""
