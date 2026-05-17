"""Text and file content extractors — simple wrappers for raw text and file input."""

from __future__ import annotations

from pathlib import Path

from src.models.score import Content, InputType


def extract_from_text(text: str, title: str | None = None) -> Content:
    """Create a Content model from raw text input.

    Args:
        text: The raw text content.
        title: Optional title for the content.

    Returns:
        A Content model with input_type=TEXT and computed hash.

    Raises:
        ValueError: If the text is empty or whitespace-only.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Cannot extract from empty text")

    content = Content(
        input_type=InputType.TEXT,
        text=cleaned,
        title=title,
    )
    content.compute_hash()

    return content


def extract_from_file(file_path: str) -> Content:
    """Read a file and create a Content model from its contents.

    Uses the filename (without extension) as the title.

    Args:
        file_path: Path to the file to read.

    Returns:
        A Content model with input_type=FILE and computed hash.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    text = path.read_text(encoding="utf-8")
    cleaned = text.strip()

    if not cleaned:
        raise ValueError(f"File is empty: {file_path}")

    # Use filename without extension as title
    title = path.stem

    content = Content(
        input_type=InputType.FILE,
        text=cleaned,
        source_url=str(path.resolve()),
        title=title,
    )
    content.compute_hash()

    return content
