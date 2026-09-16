"""Exception hierarchy for the launtel library."""


class LauntelError(Exception):
    """Base class for all launtel errors."""


class LauntelAuthError(LauntelError):
    """Raised when the portal rejects the supplied credentials."""


class LauntelSessionExpired(LauntelError):
    """Raised when a saved session cookie is no longer accepted by the portal."""


class LauntelParseError(LauntelError):
    """Raised when an authenticated page cannot be parsed into models."""


class LauntelNetworkError(LauntelError):
    """Raised for transport-level failures (DNS, TLS, timeouts, 5xx, ...)."""
