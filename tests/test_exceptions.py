"""Tests for src/core/exceptions.py — custom exceptions."""

from __future__ import annotations

import pytest

from src.core.exceptions import ExtractionError, ScoringError, StorageError


class TestScoringError:
    """Tests for ScoringError."""

    def test_can_be_raised(self):
        """ScoringError can be raised and caught."""
        with pytest.raises(ScoringError, match="scoring failed"):
            raise ScoringError("scoring failed")

    def test_inherits_from_exception(self):
        """ScoringError inherits from Exception."""
        assert issubclass(ScoringError, Exception)

    def test_message_preserved(self):
        """ScoringError preserves error message."""
        err = ScoringError("test message")
        assert str(err) == "test message"


class TestExtractionError:
    """Tests for ExtractionError."""

    def test_can_be_raised(self):
        """ExtractionError can be raised and caught."""
        with pytest.raises(ExtractionError, match="extraction failed"):
            raise ExtractionError("extraction failed")

    def test_inherits_from_exception(self):
        """ExtractionError inherits from Exception."""
        assert issubclass(ExtractionError, Exception)

    def test_message_preserved(self):
        """ExtractionError preserves error message."""
        err = ExtractionError("url not reachable")
        assert str(err) == "url not reachable"


class TestStorageError:
    """Tests for StorageError."""

    def test_can_be_raised(self):
        """StorageError can be raised and caught."""
        with pytest.raises(StorageError, match="db write failed"):
            raise StorageError("db write failed")

    def test_inherits_from_exception(self):
        """StorageError inherits from Exception."""
        assert issubclass(StorageError, Exception)

    def test_message_preserved(self):
        """StorageError preserves error message."""
        err = StorageError("connection lost")
        assert str(err) == "connection lost"


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_all_are_exceptions(self):
        """All custom exceptions are subclasses of Exception."""
        for exc_class in (ScoringError, ExtractionError, StorageError):
            assert issubclass(exc_class, Exception)

    def test_catchable_as_exception(self):
        """Custom exceptions can be caught as generic Exception."""
        try:
            raise ScoringError("test")
        except Exception as e:
            assert isinstance(e, ScoringError)
