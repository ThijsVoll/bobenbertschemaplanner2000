from __future__ import annotations

from js import XLSX, console, document  # type: ignore
from pyodide.ffi import create_proxy, to_js  # type: ignore


def get_element(element_id: str):
    """Return a browser DOM element by id."""
    return document.getElementById(element_id)


def set_status(message: str, kind: str = "info") -> None:
    """Render a status banner in the UI."""
    element = get_element("status")
    element.className = f"status status-{kind}"
    element.textContent = message
