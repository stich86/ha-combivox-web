"""Custom exceptions for Combivox integration."""


class CombivoxError(Exception):
    """Base exception for Combivox integration."""


class CombivoxConnectionError(CombivoxError):
    """Connection or HTTP error."""

    def __init__(self, message: str, status_code: int = None) -> None:
        """Initialize connection error.

        Args:
            message: Error message
            status_code: HTTP status code if available
        """
        super().__init__(message)
        self.status_code = status_code


class CombivoxAuthenticationError(CombivoxConnectionError):
    """Authentication failed."""


class CombivoxParseError(CombivoxError):
    """XML or data parsing error."""
