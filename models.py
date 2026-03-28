from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Team:
    """Represents a tournament team."""

    niveau: int
    geslacht: str
    naam: str
    leeftijd: str


@dataclass
class Match:
    """Represents a scheduled match on a field within a round."""

    ronde: int
    veld: int
    team_a: Team
    team_b: Team
