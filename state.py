from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class AppState:
    """Keeps mutable UI state and proxy references together."""

    last_result: dict[str, Any] | None = None
    output_view: str = "table"
    team_name_filter: str = ""
    team_name_filter_open: bool = False
    remove_team_proxies: List[Any] = field(default_factory=list)
    remove_pref_proxies: List[Any] = field(default_factory=list)
    event_proxies: List[Any] = field(default_factory=list)
    team_filter_proxies: List[Any] = field(default_factory=list)
