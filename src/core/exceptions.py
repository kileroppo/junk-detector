"""Custom exceptions for junk-detector."""


class ScoringError(Exception):
    """Raised when the scoring pipeline fails."""

    pass


class ExtractionError(Exception):
    """Raised when URL/content extraction fails."""

    pass


class StorageError(Exception):
    """Raised when database operations fail."""

    pass
