from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    """Represents a tournament team."""

    level: int
    gender: str
    name: str
    age: str
    matches: int


@dataclass
class Match:
    """Represents a scheduled match on a field within a round."""

    ronde: int
    veld: int
    team_a: Team
    team_b: Team
