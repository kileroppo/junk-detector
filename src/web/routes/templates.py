"""Shared Jinja2Templates instance for all route modules."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

_BASE_DIR = Path(__file__).parent.parent
_TEMPLATES_DIR = _BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
