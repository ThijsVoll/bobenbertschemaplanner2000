from __future__ import annotations

from models import Team
from sat import TournamentSchedulerSAT
from serializers import serialize_results


def _maybe_to_py(value):
    """Convert Pyodide/PyScript JsProxy values into normal Python values."""
    if hasattr(value, "to_py"):
        try:
            value = value.to_py(depth=10)
        except TypeError:
            value = value.to_py()

    if isinstance(value, dict):
        return {str(key): _maybe_to_py(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_maybe_to_py(item) for item in value]
    return value


def _team_from_dict(item: dict) -> Team:
    item = _maybe_to_py(item)
    return Team(
        level=int(item["level"]),
        gender=str(item["gender"]),
        name=str(item["name"]),
        age=str(item["age"]),
        matches=int(item["matches"]),
    )


def generate_schedule_worker(payload) -> dict:
    """Run the SAT scheduler in a background worker and return a JSON-safe result."""
    payload = _maybe_to_py(payload)

    teams = [_team_from_dict(item) for item in payload["teams"]]
    prefs = [tuple(_maybe_to_py(pair)) for pair in payload["prefs"]]
    n_rondes = int(payload["n_rondes"])
    n_velden = int(payload["n_velden"])

    scheduler = TournamentSchedulerSAT(
        teams=teams,
        preferences=prefs,
    )

    wedstrijden, rest_verplicht = scheduler.generate_schedule(
        num_rounds=n_rondes,
        num_fields=n_velden,
    )

    result = serialize_results(
        teams,
        wedstrijden,
        rest_verplicht,
        n_rondes,
    )

    return {
        "last_result": result,
        "num_matches": len(wedstrijden),
    }


__export__ = ["generate_schedule_worker"]