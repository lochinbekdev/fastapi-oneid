class OneIDError(Exception):
    """Base package exception."""


class OneIDTokenError(OneIDError):
    """Raised when OneID does not return a usable access token."""


class OneIDUpstreamError(OneIDError):
    """Raised when the upstream OneID service fails."""
