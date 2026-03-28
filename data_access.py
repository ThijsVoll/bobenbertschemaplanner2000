from __future__ import annotations

import csv
import io
import json
from typing import Optional

from browser import document, get_element
from models import Team


class InputRepository:
    """Encapsulates reads and writes to JSON and form inputs."""

    @staticmethod
    def normalize_header(value: str) -> str:
        return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")

    @classmethod
    def pick_column(cls, field_map: dict[str, str], *aliases: str) -> str:
        for alias in aliases:
            key = cls.normalize_header(alias)
            if key in field_map:
                return field_map[key]
        expected = ", ".join(aliases)
        raise ValueError(f"Missing required CSV column. Expected one of: {expected}")

    @staticmethod
    def safe_load_json_array(element_id: str) -> list:
        raw = get_element(element_id).value.strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"{element_id} must contain a JSON array.")
        return parsed

    @classmethod
    def get_team_dicts(cls) -> list[dict]:
        data = cls.safe_load_json_array("teams-json")
        teams: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each team must be a JSON object.")
            teams.append(item)
        return teams

    @classmethod
    def get_team_names(cls) -> list[str]:
        names: list[str] = []
        for item in cls.get_team_dicts():
            name = str(item.get("naam", "") or "").strip()
            if name:
                names.append(name)
        return names

    @classmethod
    def get_preferences(cls) -> list[list[str]]:
        data = cls.safe_load_json_array("prefs-json")
        prefs: list[list[str]] = []
        for pair in data:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(
                    "Each preference must be a 2-item array, e.g. ['Team A', 'Team B']"
                )
            prefs.append([str(pair[0]), str(pair[1])])
        return prefs

    @staticmethod
    def set_preferences(preferences: list[list[str]]) -> None:
        get_element("prefs-json").value = json.dumps(preferences, indent=2, ensure_ascii=False)

    @staticmethod
    def set_teams_json(teams_list: list[dict]) -> None:
        get_element("teams-json").value = json.dumps(teams_list, indent=2, ensure_ascii=False)

    @classmethod
    def parse_teams_csv_text(cls, csv_text: str) -> list[dict]:
        if not csv_text or not csv_text.strip():
            raise ValueError("The selected CSV file is empty.")

        sample = csv_text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            class DefaultDialect(csv.excel):
                delimiter = ","

            dialect = DefaultDialect

        reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("Could not read CSV headers.")

        field_map = {
            cls.normalize_header(name): name
            for name in reader.fieldnames
            if name is not None
        }
        naam_col = cls.pick_column(field_map, "naam", "team", "teamnaam", "name")
        niveau_col = cls.pick_column(field_map, "niveau", "level")
        geslacht_col = cls.pick_column(field_map, "geslacht", "gender")
        leeftijd_col = cls.pick_column(field_map, "leeftijd", "age", "leeftijdscategorie")

        teams: list[dict] = []
        for row_number, row in enumerate(reader, start=2):
            if not row:
                continue

            naam = str(row.get(naam_col, "") or "").strip()
            niveau_text = str(row.get(niveau_col, "") or "").strip()
            geslacht = str(row.get(geslacht_col, "") or "").strip()
            leeftijd = str(row.get(leeftijd_col, "") or "").strip()

            if not any([naam, niveau_text, geslacht, leeftijd]):
                continue
            if not naam:
                raise ValueError(f"CSV row {row_number}: column '{naam_col}' is empty.")
            if not niveau_text:
                raise ValueError(f"CSV row {row_number}: column '{niveau_col}' is empty.")
            if not geslacht:
                raise ValueError(f"CSV row {row_number}: column '{geslacht_col}' is empty.")
            if not leeftijd:
                raise ValueError(f"CSV row {row_number}: column '{leeftijd_col}' is empty.")

            try:
                niveau = int(niveau_text)
            except ValueError as exc:
                raise ValueError(
                    f"CSV row {row_number}: niveau must be an integer, got '{niveau_text}'."
                ) from exc

            teams.append(
                {
                    "niveau": niveau,
                    "geslacht": geslacht,
                    "naam": naam,
                    "leeftijd": leeftijd,
                }
            )

        if not teams:
            raise ValueError("No team rows were found in the CSV file.")
        return teams

    @classmethod
    def read_inputs(
        cls,
    ) -> tuple[list[Team], list[tuple[str, str]], int, int, Optional[int]]:
        teams_raw = cls.safe_load_json_array("teams-json")
        prefs_raw = cls.safe_load_json_array("prefs-json")
        n_rondes = int(get_element("n-rondes").value)
        n_velden = int(get_element("n-velden").value)
        seed_text = get_element("seed").value.strip()
        seed = int(seed_text) if seed_text else None

        teams: list[Team] = []
        for item in teams_raw:
            if not isinstance(item, dict):
                raise ValueError("Each team must be a JSON object.")
            teams.append(
                Team(
                    niveau=int(item["niveau"]),
                    geslacht=str(item["geslacht"]),
                    naam=str(item["naam"]),
                    leeftijd=str(item["leeftijd"]),
                )
            )

        prefs: list[tuple[str, str]] = []
        for pair in prefs_raw:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(
                    "Each preference must contain exactly 2 team names."
                )
            prefs.append((str(pair[0]), str(pair[1])))
        return teams, prefs, n_rondes, n_velden, seed
