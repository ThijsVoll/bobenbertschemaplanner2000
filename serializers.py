from __future__ import annotations

from collections import defaultdict

from models import Match, Team


def serialize_results(
    teams: list[Team],
    wedstrijden: list[Match],
    rest_verplicht: dict[str, int],
    rest_opt: dict[str, int],
    n_rondes: int,
) -> dict:
    return {
        "n_rondes": n_rondes,
        "teams": [
            {
                "naam": team.naam,
                "geslacht": team.geslacht,
                "leeftijd": team.leeftijd,
                "niveau": team.niveau,
            }
            for team in teams
        ],
        "matches": [
            {
                "ronde": match.ronde,
                "veld": match.veld,
                "team_a": {
                    "naam": match.team_a.naam,
                    "geslacht": match.team_a.geslacht,
                    "leeftijd": match.team_a.leeftijd,
                    "niveau": match.team_a.niveau,
                },
                "team_b": {
                    "naam": match.team_b.naam,
                    "geslacht": match.team_b.geslacht,
                    "leeftijd": match.team_b.leeftijd,
                    "niveau": match.team_b.niveau,
                },
            }
            for match in wedstrijden
        ],
        "remaining_required": rest_verplicht,
        "remaining_optional": rest_opt,
    }


def build_excel_overview_rows(results: dict) -> list[list]:
    matches = results.get("matches", [])
    teams = results.get("teams", [])
    rounds_used = sorted({int(match["ronde"]) for match in matches})
    return [
        ["Metric", "Value"],
        ["Aantal teams", len(teams)],
        ["Aantal wedstrijden", len(matches)],
        ["Rondes gebruikt", len(rounds_used)],
        ["Geconfigureerde rondes", int(results.get("n_rondes", 0) or 0)],
        ["Open verplichte slots", sum(results.get("remaining_required", {}).values())],
    ]


def build_excel_matches_rows(results: dict) -> list[list]:
    rows = [[
        "Ronde",
        "Veld",
        "Team A",
        "Team A Geslacht",
        "Team A Leeftijd",
        "Team A Niveau",
        "Team B",
        "Team B Geslacht",
        "Team B Leeftijd",
        "Team B Niveau",
    ]]
    for match in sorted(results.get("matches", []), key=lambda item: (item["ronde"], item["veld"])):
        rows.append([
            int(match["ronde"]),
            int(match["veld"]),
            str(match["team_a"]["naam"]),
            str(match["team_a"]["geslacht"]),
            str(match["team_a"]["leeftijd"]),
            int(match["team_a"]["niveau"]),
            str(match["team_b"]["naam"]),
            str(match["team_b"]["geslacht"]),
            str(match["team_b"]["leeftijd"]),
            int(match["team_b"]["niveau"]),
        ])
    return rows


def build_excel_timeline_rows(results: dict) -> list[list]:
    teams = results.get("teams", [])
    matches = results.get("matches", [])
    n_rondes = int(results.get("n_rondes", 0) or 0)
    timeline_lookup: dict[str, dict[int, str]] = defaultdict(dict)
    for match in matches:
        ronde = int(match["ronde"])
        veld = int(match["veld"])
        team_a = match["team_a"]
        team_b = match["team_b"]
        timeline_lookup[str(team_a["naam"])][ronde] = f"{team_b['naam']} (Veld {veld:02d})"
        timeline_lookup[str(team_b["naam"])][ronde] = f"{team_a['naam']} (Veld {veld:02d})"

    header = ["Team", "Geslacht", "Leeftijd", "Niveau"]
    header.extend([f"Ronde {ronde}" for ronde in range(1, n_rondes + 1)])
    rows = [header]
    sorted_teams = sorted(
        teams,
        key=lambda team: (
            int(team.get("niveau", 0)),
            str(team.get("geslacht", "")),
            str(team.get("naam", "")),
        ),
    )
    for team in sorted_teams:
        team_name = str(team["naam"])
        row = [
            team_name,
            str(team["geslacht"]),
            str(team["leeftijd"]),
            int(team["niveau"]),
        ]
        for ronde in range(1, n_rondes + 1):
            row.append(timeline_lookup.get(team_name, {}).get(ronde, ""))
        rows.append(row)
    return rows


def build_excel_remaining_rows(results: dict) -> list[list]:
    rows = [["Team", "Required left", "Optional left"]]
    required = results.get("remaining_required", {})
    optional = results.get("remaining_optional", {})
    for name in sorted(required):
        rows.append([str(name), int(required.get(name, 0)), int(optional.get(name, 0))])
    return rows
