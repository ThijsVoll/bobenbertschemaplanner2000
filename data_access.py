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
            name = str(item.get("name", "") or "").strip()
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
        name_col = cls.pick_column(field_map, "naam")
        level_col = cls.pick_column(field_map, "niveau")
        gender_col = cls.pick_column(field_map, "geslacht")
        age_col = cls.pick_column(field_map, "leeftijd")
        wedstrijden_col = cls.pick_column(field_map, "wedstrijden")

        teams: list[dict] = []
        for row_number, row in enumerate(reader, start=2):
            if not row:
                continue

            name = str(row.get(name_col, "") or "").strip()
            level_text = str(row.get(level_col, "") or "").strip()
            gender = str(row.get(gender_col, "") or "").strip()
            age = str(row.get(age_col, "") or "").strip()
            wedstrijden_text = str(row.get(wedstrijden_col, "") or "").strip()

            if not any([name, level_text, gender, age]):
                continue
            if not name:
                raise ValueError(f"CSV row {row_number}: column '{name_col}' is empty.")
            if not level_text:
                raise ValueError(f"CSV row {row_number}: column '{level_col}' is empty.")
            if not gender:
                raise ValueError(f"CSV row {row_number}: column '{gender_col}' is empty.")
            if not age:
                raise ValueError(f"CSV row {row_number}: column '{age_col}' is empty.")
            if not wedstrijden_text:
                raise ValueError(f"CSV row {row_number}: column '{wedstrijden_col}' is empty.")
            
            try:
                level = int(level_text)
            except ValueError as exc:
                raise ValueError(
                    f"CSV row {row_number}: level must be an integer, got '{level_text}'."
                ) from exc

            try:
                wedstrijden = int(wedstrijden_text)
            except ValueError as exc:
                raise ValueError(
                    f"CSV row {row_number}: level must be an integer, got '{wedstrijden_text}'."
                ) from exc
            
            teams.append(
                {
                    "level": level,
                    "gender": gender,
                    "name": name,
                    "age": age,
                    "wedstrijden": wedstrijden
                }
            )

        if not teams:
            raise ValueError("No team rows were found in the CSV file.")
        return teams

    @classmethod
    def parse_prefs_csv_text(cls, csv_text: str) -> list[dict]:
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

        team_a_col = cls.pick_column(field_map, "teama")
        team_b_col = cls.pick_column(field_map, "teamb")

        prefs = []
        for row_number, row in enumerate(reader, start=2):
            if not row:
                continue

            team_a = str(row.get(team_a_col, "") or "").strip().replace("\u200b", "")
            team_b = str(row.get(team_b_col, "") or "").strip().replace("\u200b", "")
           
            if not any([team_a, team_b]):
                continue
            if not team_a:
                raise ValueError(f"CSV row {row_number}: column 'teamA' is empty.")
            if not team_b:
                raise ValueError(f"CSV row {row_number}: column 'teamB' is empty.")
            prefs.append(
                [team_a, team_b]
    
            )

        if not prefs:
            raise ValueError("No preference rows were found in the CSV file.")
        return prefs
    
    @classmethod
    def read_inputs(
        cls,
    ) -> tuple[list[Team], list[tuple[str, str]], int, int, Optional[int]]:
        teams_raw = cls.safe_load_json_array("teams-json")
        prefs_raw = cls.safe_load_json_array("prefs-json")
        n_rondes = int(get_element("n-rondes").value)
        n_velden = int(get_element("n-velden").value)

        teams: list[Team] = []
        for item in teams_raw:
            if not isinstance(item, dict):
                raise ValueError("Each team must be a JSON object.")
            teams.append(
                Team(
                    level=int(item["level"]),
                    gender=str(item["gender"]),
                    name=str(item["name"]),
                    age=str(item["age"]),
                    matches=int(item["wedstrijden"]),
                )
            )

        prefs: list[tuple[str, str]] = []
        for pair in prefs_raw:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(
                    "Each preference must contain exactly 2 team names."
                )
            prefs.append((str(pair[0]), str(pair[1])))
        return teams, prefs, n_rondes, n_velden
